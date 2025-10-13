# human_resource/tasks.py

import openpyxl
import random
import string
from celery import shared_task
from django.db import transaction
from django.contrib.auth.models import Group, User
from .models import StaffModel, StaffProfileModel, StaffUploadTask
# Import the helper function we defined in views.py
#from human_resource.views import _send_credentials_email


@shared_task(bind=True)
def process_staff_upload(self, file_path):
    tracker = StaffUploadTask.objects.get(task_id=self.request.id)
    tracker.status = StaffUploadTask.Status.PROCESSING
    tracker.save(update_fields=['status'])

    try:
        workbook = openpyxl.load_workbook(file_path, data_only=True)
        sheet = workbook.active

        header_row = [cell.value for cell in sheet[1]]
        header_map = {str(header).strip(): idx for idx, header in enumerate(header_row)}
        if not all(k in header_map for k in ['first_name', 'last_name', 'gender']):
            raise ValueError("Missing required columns: first_name, last_name, gender")

        created_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0

        for row_index, row_cells in enumerate(sheet.iter_rows(min_row=2), start=2):
            try:
                def get_cell_value(col_name):
                    cell_index = header_map.get(col_name)
                    if cell_index is None: return ''
                    cell_value = row_cells[cell_index].value
                    return str(cell_value).strip() if cell_value is not None else ''

                first_name = get_cell_value('first_name')
                last_name = get_cell_value('last_name')
                gender = get_cell_value('gender').upper()

                if not all([first_name, last_name, gender]):
                    failed_count += 1
                    continue

                email = get_cell_value('email').lower() or None
                mobile = get_cell_value('mobile') or None
                group_name = get_cell_value('group_name')

                user_group = None
                if group_name:
                    user_group = Group.objects.filter(name__iexact=group_name).first()

                try:
                    staff_member = StaffModel.objects.get(
                        first_name__iexact=first_name, last_name__iexact=last_name, gender__iexact=gender
                    )
                    # ... (Your update logic for existing staff goes here) ...
                    updated_count += 1

                except StaffModel.DoesNotExist:
                    with transaction.atomic():
                        staff_member = StaffModel.objects.create(
                            first_name=first_name, last_name=last_name, gender=gender,
                            email=email, mobile=mobile, group=user_group
                        )
                        created_count += 1

                        # ===== ADDED USER CREATION LOGIC =====
                        try:
                            username = staff_member.staff_id
                            if User.objects.filter(username=username).exists():
                                username = f"{username}-{random.randint(100, 999)}"

                            password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

                            user = User.objects.create_user(
                                username=username, password=password,
                                first_name=staff_member.first_name, last_name=staff_member.last_name,
                                email=staff_member.email or ''
                            )

                            StaffProfileModel.objects.create(
                                user=user, staff=staff_member, default_password=password
                            )

                            if staff_member.group:
                                staff_member.group.user_set.add(user)

                            

                        except Exception as user_creation_error:
                            print(
                                f"Staff '{staff_member}' created, but FAILED to create user account: {user_creation_error}")
                        # ===== END OF ADDED LOGIC =====

            except Exception as e:
                failed_count += 1
                print(f"Error processing row {row_index}: {e}")

        result_message = (
            f"Processing complete. Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}, Failed: {failed_count}.")
        tracker.status = StaffUploadTask.Status.SUCCESS
        tracker.result = result_message
        tracker.save(update_fields=['status', 'result'])
        return result_message

    except Exception as e:
        error_message = f"A critical error occurred: {e}"
        tracker.status = StaffUploadTask.Status.FAILURE
        tracker.result = error_message
        tracker.save(update_fields=['status', 'result'])
        raise e