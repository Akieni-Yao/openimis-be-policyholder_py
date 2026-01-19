from celery import shared_task
import logging
import os
import hashlib
import pandas as pd
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone

from core.models import User
from core.constants import INS_ADDED_NT
from core.notification_service import create_camu_notification

from policyholder.models import (
    PolicyHolder,
    PolicyHolderContributionPlan,
    PolicyHolderInsuree,
    PolicyHolderInsureeBatchUpload,
    PolicyHolderInsureeUploadedFile,
)
from policyholder.erp_intigration import erp_create_update_policyholder
from policyholder.utils import Utils
from policyholder.dms_utils import validate_enrolment_type

# --- IMPORT SHARED UTILS (Breaks Circular Dependency) ---
from policyholder.import_utils import (
    get_policy_holder_from_code,
    get_or_create_insuree_from_line,
    soft_delete_insuree,
    get_village_from_line,
    get_or_create_family_from_line,
    validating_insuree_on_name_dob,
    check_for_category_change_request,
    clean_line,
    HEADER_INSUREE_ID,
    HEADER_INSUREE_CAMU_NO,
    HEADER_INSUREE_DOB,
    HEADER_DELETE,
    HEADER_FAMILY_LOCATION_CODE,
    HEADER_INSUREE_OTHER_NAMES,
    HEADER_INSUREE_LAST_NAME,
    HEADER_BIRTH_LOCATION_CODE,
    HEADER_INSUREE_GENDER,
    HEADER_CIVILITY,
    HEADER_PHONE,
    HEADER_ADDRESS,
    HEADER_EMAIL,
    MINIMUM_AGE_LIMIT,
    MINIMUM_AGE_LIMIT_FOR_STUDENTS,
)

from insuree.dms_utils import send_mail_to_temp_insuree_with_pdf
from rest_api.lib.file_bucket import download_file_from_s3_bucket

logger = logging.getLogger(__name__)


@shared_task
def sync_policyholders_to_erp():
    user = User.objects.get(username="System")

    policyholders = Utils.get_policyholders_missing_erp()
    logger.info(f"Found {policyholders.count()} policyholders to sync.")

    for ph in policyholders:
        try:
            phcp = PolicyHolderContributionPlan.objects.filter(
                policy_holder=ph, is_deleted=False
            ).first()

            if not phcp:
                logger.warning(f"No Contribution Plan found for PolicyHolder ID: {ph.id}")
                continue
            result = erp_create_update_policyholder(ph.id, phcp.contribution_plan_bundle.id, user)

            if not result:
                logger.error(f"Failed to process PolicyHolder ID: {ph.id}. Continuing...")
        except Exception as e:
            logger.exception(f"Error processing PolicyHolder ID: {ph.id}. Skipping...")

    logger.info("Sync process completed.")


def build_result_entry(line, index, chf_id, status, nom="", prenom=""):
    """
    Build a result entry in the format: ligne, numero_camu, nom, prenom, Etat, remarque
    """
    etat = "OK" if status in ["Succès", "Aucun changement"] else "KO"
    remarque = "-" if status == "Succès" else status

    if chf_id and pd.notna(chf_id):
        chf_id_str = str(chf_id)
        # Clean up float-like strings (e.g. "12345.0" -> "12345")
        if '.' in chf_id_str and chf_id_str.replace('.', '', 1).replace('-', '', 1).isdigit():
            try:
                chf_id_str = str(int(float(chf_id_str)))
            except (ValueError, OverflowError):
                pass
        numero_camu = chf_id_str
    else:
        numero_camu = ""

    return {
        "ligne": index + 1,
        "numero_camu": numero_camu,
        "nom": nom,
        "prenom": prenom,
        "Etat": etat,
        "remarque": remarque,
    }

@shared_task(bind=True)
def import_policyholder_insurees_async(
    self, user_id, policyholder_code, batch_upload_id, uploaded_file_record_id
):
    """
    Asynchronous task to import policyholder insurees from Excel file.
    """
    batch_upload = None
    results_data = []
    total_rows = 0

    try:
        batch_upload = PolicyHolderInsureeBatchUpload.objects.get(id=batch_upload_id)
        user = User.objects.get(id=user_id)
        policyholder = get_policy_holder_from_code(policyholder_code)
        core_username = user.username
        user_id_for_audit = user.id_for_audit

        if not policyholder:
            raise Exception("Policy holder not found")

        # Get contribution plan bundle
        ph_cpb = PolicyHolderContributionPlan.objects.filter(
            policy_holder=policyholder, is_deleted=False
        ).first()

        if not ph_cpb:
            raise Exception("No contribution plan bundle found for policyholder")

        cpb = ph_cpb.contribution_plan_bundle
        enrolment_type = cpb.name if cpb else None

        # Download file from S3
        uploaded_file_record = PolicyHolderInsureeUploadedFile.objects.filter(
            id=uploaded_file_record_id
        ).first()

        if not uploaded_file_record:
            raise Exception("Uploaded file record not found")

        if not uploaded_file_record.file_path:
            raise Exception("Uploaded file record has no file path")

        # Use MEDIA_ROOT if available, otherwise use temp directory
        base_path = settings.MEDIA_ROOT
        if not base_path:
            import tempfile
            base_path = tempfile.gettempdir()

        # Ensure the directory exists
        download_dir = os.path.join(base_path, "policyholder", "insuree_import")
        os.makedirs(download_dir, exist_ok=True)

        download_path = os.path.join(
            download_dir,
            os.path.basename(uploaded_file_record.file_path),
        )

        file_path = download_file_from_s3_bucket(
            object_key=f"policyholder/{uploaded_file_record.file_path}",
            download_path=download_path,
        )

        if not file_path or not os.path.exists(file_path):
            # Fallback: sometimes bucket function returns None but downloads
            if not os.path.exists(download_path):
                raise Exception("Failed to download file from S3 bucket")
            file_path = download_path

        # Read Excel file
        df = pd.read_excel(file_path)
        df.columns = [col.strip() for col in df.columns]

        # Rename columns using constants from import_utils
        rename_columns = {
            "Numéro CAMU": HEADER_INSUREE_CAMU_NO,
            "Prénom": HEADER_INSUREE_OTHER_NAMES,
            "Nom": HEADER_INSUREE_LAST_NAME,
            "Numéro CAMU temporaire": HEADER_INSUREE_ID,
            "Date de naissance": HEADER_INSUREE_DOB,
            "Lieu de naissance": HEADER_BIRTH_LOCATION_CODE,
            "Sexe": HEADER_INSUREE_GENDER,
            "Civilité": HEADER_CIVILITY,
            "Téléphone": HEADER_PHONE,
            "Adresse": HEADER_ADDRESS,
            "Village": HEADER_FAMILY_LOCATION_CODE,
            "Email": HEADER_EMAIL,
            "Supprimé": HEADER_DELETE,
        }

        df.rename(columns=rename_columns, inplace=True)

        # Set total number of rows for progress tracking
        total_rows = len(df)
        batch_upload.mark_as_processing(total_rows)

        # Initialize counters
        success_count = 0
        error_count = 0

        # Process each row
        for index, row in df.iterrows():
            try:
                clean_line(row)

                current_minimum_age = MINIMUM_AGE_LIMIT
                if cpb.code == "PSC05" or enrolment_type == "Etudiants":
                    current_minimum_age = MINIMUM_AGE_LIMIT_FOR_STUDENTS

                if not row.get(HEADER_INSUREE_ID) and not row.get(HEADER_INSUREE_CAMU_NO):
                    dob_value = row.get(HEADER_INSUREE_DOB)
                    if dob_value:
                        date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]
                        dob = None
                        
                        if isinstance(dob_value, datetime):
                            dob = dob_value
                        else:
                            for date_format in date_formats:
                                try:
                                    dob = datetime.strptime(str(dob_value), date_format)
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        if dob is None:
                            error = f"Format de date invalide: {dob_value}"
                            chf_id = row.get(HEADER_INSUREE_ID) or row.get(HEADER_INSUREE_CAMU_NO) or ""
                            nom = row.get(HEADER_INSUREE_LAST_NAME, "")
                            prenom = row.get(HEADER_INSUREE_OTHER_NAMES, "")
                            results_data.append(
                                build_result_entry(row, index, chf_id, error, nom, prenom)
                            )
                            error_count += 1
                            continue
                        
                        age = (datetime.now().date() - dob.date()) // timedelta(days=365.25)
                        if age < current_minimum_age:
                            error = f"L'assuré doit être âgé d'au moins {current_minimum_age} ans."
                            chf_id = row.get(HEADER_INSUREE_ID) or row.get(HEADER_INSUREE_CAMU_NO) or ""
                            nom = row.get(HEADER_INSUREE_LAST_NAME, "")
                            prenom = row.get(HEADER_INSUREE_OTHER_NAMES, "")
                            results_data.append(
                                build_result_entry(row, index, chf_id, error, nom, prenom)
                            )
                            error_count += 1
                            continue
                    
                    existing_insuree = validating_insuree_on_name_dob(row, policyholder)
                    if existing_insuree:
                        error = "Un assuré ayant le même nom et la même date de naissance existe déjà, veuillez ajouter son numéro CAMU ou numéro temporaire."
                        chf_id = row.get(HEADER_INSUREE_ID) or row.get(HEADER_INSUREE_CAMU_NO) or ""
                        nom = row.get(HEADER_INSUREE_LAST_NAME, "")
                        prenom = row.get(HEADER_INSUREE_OTHER_NAMES, "")
                        results_data.append(
                            build_result_entry(row, index, chf_id, error, nom, prenom)
                        )
                        error_count += 1
                        continue

                if row.get(HEADER_DELETE) and str(row.get(HEADER_DELETE)).lower() in ["true", "1", "oui", "yes"]:
                    deleted = soft_delete_insuree(row, policyholder.code, user_id_for_audit)
                    chf_id = row.get(HEADER_INSUREE_ID) or row.get(HEADER_INSUREE_CAMU_NO) or ""
                    nom = row.get(HEADER_INSUREE_LAST_NAME, "")
                    prenom = row.get(HEADER_INSUREE_OTHER_NAMES, "")
                    if deleted:
                        results_data.append(
                            build_result_entry(row, index, chf_id, "Supprimé avec succès", nom, prenom)
                        )
                        success_count += 1
                    else:
                        results_data.append(
                            build_result_entry(row, index, chf_id, "Erreur: Assuré non trouvé", nom, prenom)
                        )
                        error_count += 1
                    continue

                village = get_village_from_line(row)
                if not village:
                    error = f"Village inconnu - {row.get(HEADER_FAMILY_LOCATION_CODE, '')}"
                    chf_id = row.get(HEADER_INSUREE_ID) or row.get(HEADER_INSUREE_CAMU_NO) or ""
                    nom = row.get(HEADER_INSUREE_LAST_NAME, "")
                    prenom = row.get(HEADER_INSUREE_OTHER_NAMES, "")
                    results_data.append(
                        build_result_entry(row, index, chf_id, error, nom, prenom)
                    )
                    error_count += 1
                    continue

                is_valid_enrolment = validate_enrolment_type(row, enrolment_type)
                if not is_valid_enrolment:
                    error = "Le type d'enrôlement doit être différent de 'étudiant."
                    chf_id = row.get(HEADER_INSUREE_ID) or row.get(HEADER_INSUREE_CAMU_NO) or ""
                    nom = row.get(HEADER_INSUREE_LAST_NAME, "")
                    prenom = row.get(HEADER_INSUREE_OTHER_NAMES, "")
                    results_data.append(
                        build_result_entry(row, index, chf_id, error, nom, prenom)
                    )
                    error_count += 1
                    continue

                # CRITICAL: Pass 'user' object to utility function
                insuree, error = get_or_create_insuree_from_line(
                    row,
                    village,
                    user_id_for_audit,
                    user, # Pass the User object
                    user.id,
                    enrolment_type,
                )

                if error:
                    chf_id = row.get(HEADER_INSUREE_ID) or row.get(HEADER_INSUREE_CAMU_NO) or ""
                    nom = row.get(HEADER_INSUREE_LAST_NAME, "")
                    prenom = row.get(HEADER_INSUREE_OTHER_NAMES, "")
                    results_data.append(
                        build_result_entry(row, index, chf_id, error, nom, prenom)
                    )
                    error_count += 1
                    continue

                family, family_created = get_or_create_family_from_line(
                    row, user_id_for_audit, enrolment_type, insuree, village
                )

                if not family:
                    error = "Impossible de créer ou de trouver la famille."
                    chf_id = row.get(HEADER_INSUREE_ID) or row.get(HEADER_INSUREE_CAMU_NO) or ""
                    nom = row.get(HEADER_INSUREE_LAST_NAME, "")
                    prenom = row.get(HEADER_INSUREE_OTHER_NAMES, "")
                    results_data.append(
                        build_result_entry(row, index, chf_id, error, nom, prenom)
                    )
                    error_count += 1
                    continue

                # Category Change Request
                try:
                    check_for_category_change_request(user, row, policyholder, enrolment_type)
                except Exception as e:
                    logger.warning(f"Error in check_for_category_change_request: {e}")

                phi_json_ext = {}
                employer_number = None

                phi = PolicyHolderInsuree.objects.filter(
                    insuree=insuree, policy_holder=policyholder
                ).first()

                if phi:
                    phi._state.adding = True
                    if (
                        phi.contribution_plan_bundle != cpb
                        or phi.employer_number != employer_number
                        or phi.json_ext != phi_json_ext
                    ):
                        phi.contribution_plan_bundle = cpb
                        phi.employer_number = employer_number
                        phi.json_ext = phi_json_ext
                        phi.save(username=core_username)
                else:
                    # Create new record
                    phi = PolicyHolderInsuree(
                        insuree=insuree,
                        policy_holder=policyholder,
                        contribution_plan_bundle=cpb,
                        json_ext=phi_json_ext,
                        employer_number=employer_number,
                    )
                    phi.save(username=core_username)

                try:
                    create_camu_notification(INS_ADDED_NT, phi)
                except Exception as e:
                    logger.error(f"Failed to create CAMU notification: {e}")

                try:
                    if insuree.email:
                        insuree_enrolment_type = insuree.json_ext.get("insureeEnrolmentType", "").lower()
                        if insuree_enrolment_type:
                            send_mail_to_temp_insuree_with_pdf(insuree, insuree_enrolment_type)
                except Exception as e:
                    logger.error(f"Fail to send auto mail: {e}")

                chf_id = insuree.chf_id or insuree.camu_number or ""
                nom = insuree.last_name or ""
                prenom = insuree.other_names or ""
                results_data.append(
                    build_result_entry(row, index, chf_id, "Succès", nom, prenom)
                )
                success_count += 1

            except Exception as e:
                logger.error(f"Error processing row {index + 1}: {str(e)}", exc_info=True)
                chf_id = row.get(HEADER_INSUREE_ID) or row.get(HEADER_INSUREE_CAMU_NO) or ""
                nom = row.get(HEADER_INSUREE_LAST_NAME, "")
                prenom = row.get(HEADER_INSUREE_OTHER_NAMES, "")
                results_data.append(
                    build_result_entry(row, index, chf_id, f"Erreur: {str(e)}", nom, prenom)
                )
                error_count += 1

            # Update progress
            batch_upload.update_progress(
                processed_rows=index + 1,
                success_count=success_count,
                error_count=error_count,
            )

        batch_upload.success_count = success_count
        batch_upload.error_count = error_count
        batch_upload.results = {"results": results_data}
        batch_upload.mark_as_completed()
        batch_upload.save(update_fields=["results", "success_count", "error_count", "status", "completed_at", "updated_at"])

        # Clean up downloaded file
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.warning(f"Failed to clean up temp file: {e}")

        return {
            "success": True,
            "total_rows": total_rows,
            "success_count": success_count,
            "error_count": error_count,
        }

    except Exception as e:
        logger.error(f"Fatal error in import_policyholder_insurees_async: {str(e)}", exc_info=True)

        if batch_upload:
            batch_upload.mark_as_failed(str(e))

        raise