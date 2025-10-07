# hr_management/tasks.py

import openpyxl
from celery import shared_task
from django.db import transaction
from django.contrib.auth.models import Group
from .models import StaffModel


@shared_task
def process_staff_upload(file_path):
    """
    Processes an uploaded Excel file using openpyxl.
    - If staff (FirstName, LastName, Gender) exists, it updates mobile/email.
    - If staff does not exist, it creates a new one.
    - A post_save signal on StaffModel handles User creation for NEW staff.
    """
    try:
        workbook = openpyxl.load_workbook(file_path, data_only=True)
        sheet = workbook.active

        header_row = [cell.value for cell in sheet[1]]
        try:
            header_map = {header.strip(): idx for idx, header in enumerate(header_row)}
            if not all(k in header_map for k in ['first_name', 'last_name', 'gender']):
                raise ValueError("Missing required columns: first_name, last_name, gender")
        except Exception as e:
            print(f"Error reading header row: {e}")
            return f"Error reading header row: {e}"

        created_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0

        for row_index, row_cells in enumerate(sheet.iter_rows(min_row=2), start=2):
            try:
                with transaction.atomic():
                    def get_cell_value(col_name):
                        cell_index = header_map.get(col_name)
                        if cell_index is None: return ''
                        cell_value = row_cells[cell_index].value
                        return str(cell_value).strip() if cell_value is not None else ''

                    first_name = get_cell_value('first_name')
                    last_name = get_cell_value('last_name')
                    gender = get_cell_value('gender').upper()

                    if not all([first_name, last_name, gender]):
                        print(f"Skipping row {row_index} due to missing required fields.")
                        failed_count += 1
                        continue

                    # --- Get optional data and Group ---
                    email = get_cell_value('email').lower() or None
                    mobile = get_cell_value('mobile') or None
                    group_name = get_cell_value('group_name')

                    user_group = None
                    if group_name:
                        try:
                            user_group = Group.objects.get(name__iexact=group_name)
                        except Group.DoesNotExist:
                            print(f"Group '{group_name}' not found for row {row_index}. Staff will have no group.")

                    # --- NEW: UPDATE OR CREATE LOGIC ---
                    try:
                        # UPDATE PATH: Try to find an existing staff member
                        staff_member = StaffModel.objects.get(
                            first_name__iexact=first_name,
                            last_name__iexact=last_name,
                            gender__iexact=gender
                        )

                        fields_to_update = []
                        # Check if mobile number needs updating
                        if staff_member.mobile != (mobile or ''):
                            staff_member.mobile = mobile
                            fields_to_update.append('mobile')

                        # Check if email needs updating
                        if staff_member.email != email:
                            staff_member.email = email
                            fields_to_update.append('email')
                            # Also update the associated user's email since signals don't run on .save()
                            if hasattr(staff_member, 'staff_profile') and staff_member.staff_profile:
                                user = staff_member.staff_profile.user
                                user.email = email if email else ''
                                user.save(update_fields=['email'])

                        # Check if group needs updating
                        if staff_member.group != user_group:
                            staff_member.group = user_group
                            fields_to_update.append('group')
                            # Also update the user's group membership
                            if hasattr(staff_member, 'staff_profile') and staff_member.staff_profile:
                                user = staff_member.staff_profile.user
                                user.groups.set([user_group] if user_group else [])

                        if fields_to_update:
                            staff_member.save(update_fields=fields_to_update)
                            print(
                                f"Updated Staff ID {staff_member.staff_id} ({first_name} {last_name}) with new info for: {fields_to_update}")
                            updated_count += 1
                        else:
                            print(f"Staff ({first_name} {last_name}) already exists and is up-to-date. Skipping.")
                            skipped_count += 1

                    except StaffModel.DoesNotExist:
                        # CREATE PATH: If no staff member was found, create one
                        StaffModel.objects.create(
                            first_name=first_name,
                            last_name=last_name,
                            gender=gender,
                            email=email,
                            mobile=mobile,
                            group=user_group
                        )
                        print(f"Creating new staff: {first_name} {last_name}")
                        created_count += 1

            except Exception as e:
                print(f"Error processing row {row_index}: {e}")
                failed_count += 1

        result = (f"Processing complete. "
                  f"Created: {created_count}, Updated: {updated_count}, "
                  f"Skipped: {skipped_count}, Failed: {failed_count}.")
        print(result)
        return result

    except Exception as e:
        print(f"A critical error occurred: {e}")
        return "A critical error occurred during file processing."