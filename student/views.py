import logging
import io
import json
import base64

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.views import View
from xlsxwriter import Workbook
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
)

from admin_site.models import ClassesModel, ClassSectionModel
from .models import StudentModel, ParentModel, StudentSettingModel, FingerprintModel
from .forms import StudentForm, ParentForm, StudentSettingForm

logger = logging.getLogger(__name__)


# -------------------------
# Student Setting Views (Singleton)
# -------------------------
class StudentSettingDetailView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'student.view_studentsettingmodel'
    template_name = 'student/setting/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['student_setting'] = StudentSettingModel.objects.first()
        return context


class StudentSettingCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = StudentSettingModel
    permission_required = 'student.add_studentsettingmodel'
    form_class = StudentSettingForm
    template_name = 'student/setting/create.html'

    def get_success_url(self):
        return reverse('setting_detail')

    def dispatch(self, request, *args, **kwargs):
        if StudentSettingModel.objects.exists():
            return redirect(reverse('setting_edit'))
        return super().dispatch(request, *args, **kwargs)


class StudentSettingUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = StudentSettingModel
    permission_required = 'student.change_studentsettingmodel'
    form_class = StudentSettingForm
    template_name = 'student/setting/create.html'

    def get_object(self, queryset=None):
        return StudentSettingModel.objects.first()

    def get_success_url(self):
        return reverse('setting_detail')


# -------------------------
# Parent Views
# -------------------------
class ParentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ParentModel
    permission_required = 'student.view_parentmodel'
    template_name = 'student/parent/index.html'
    context_object_name = "parent_list"
    queryset = ParentModel.objects.all().order_by('first_name')


class ParentCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ParentModel
    permission_required = 'student.add_parentmodel'
    form_class = ParentForm
    template_name = 'student/parent/create.html'

    def get_success_url(self):
        action = self.request.POST.get('action')
        if action == 'save_and_add_ward':
            messages.success(self.request, "Parent created successfully. Now, please register their first ward.")
            return reverse('student_create', kwargs={'parent_pk': self.object.pk})
        messages.success(self.request, "Parent created successfully.")
        return reverse('parent_detail', kwargs={'pk': self.object.pk})


class ParentDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ParentModel
    permission_required = 'student.view_parentmodel'
    template_name = 'student/parent/detail.html'
    context_object_name = "parent"


class ParentUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = ParentModel
    permission_required = 'student.change_parentmodel'
    form_class = ParentForm
    template_name = 'student/parent/edit.html'
    context_object_name = "parent"

    def get_success_url(self):
        messages.success(self.request, "Parent details updated successfully.")
        return reverse('parent_detail', kwargs={'pk': self.object.pk})


class ParentDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ParentModel
    permission_required = 'student.delete_parentmodel'
    template_name = 'student/parent/delete.html'
    context_object_name = "parent"

    def get_success_url(self):
        messages.success(self.request, "Parent deleted successfully.")
        return reverse('parent_index')


# -------------------------
# Student Views
# -------------------------
class ClassStudentSelectView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    Displays a form for the user to select a class and section to view.
    """
    permission_required = 'student.view_studentmodel'
    template_name = 'student/student/select_class.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['class_list'] = ClassesModel.objects.all().order_by('name')
        return context


class StudentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    This view now handles both displaying ALL students and displaying a
    FILTERED list of students based on a class and section.
    """
    model = StudentModel
    permission_required = 'student.view_studentmodel'
    template_name = 'student/student/index.html'
    context_object_name = "student_list"

    def get_queryset(self):
        queryset = StudentModel.objects.select_related('parent', 'student_class', 'class_section').all()

        # Check if class and section filters are present in the URL
        class_id = self.request.GET.get('class')
        section_id = self.request.GET.get('section')

        if class_id and section_id:
            # If filters are present, apply them to the queryset
            return queryset.filter(student_class_id=class_id, class_section_id=section_id).order_by('first_name')

        # Otherwise, return all active students
        return queryset.filter(status='active').order_by('first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        class_id = self.request.GET.get('class')
        section_id = self.request.GET.get('section')

        # Add the selected class and section to the context for display in the template
        if class_id and section_id:
            context['selected_class'] = get_object_or_404(ClassesModel, pk=class_id)
            context['selected_section'] = get_object_or_404(ClassSectionModel, pk=section_id)

        return context


class StudentCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = StudentModel
    permission_required = 'student.add_studentmodel'
    form_class = StudentForm
    template_name = 'student/student/create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['parent'] = get_object_or_404(ParentModel, pk=self.kwargs.get('parent_pk'))
        return context

    def form_valid(self, form):
        parent = get_object_or_404(ParentModel, pk=self.kwargs.get('parent_pk'))
        form.instance.parent = parent
        messages.success(self.request, f"Student '{form.instance.first_name}' registered successfully for {parent}.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('student_detail', kwargs={'pk': self.object.pk})


class StudentDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = StudentModel
    permission_required = 'student.view_studentmodel'
    template_name = 'student/student/detail.html'
    context_object_name = "student"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add the following line to pass the fingerprint list to the template
        context['fingerprint_list'] = self.object.fingerprints.all().order_by('-created_at')

        # Get settings for fingerprint limits
        max_fingerprints = 4
        can_add_more = context['fingerprint_list'].count() < max_fingerprints

        context['can_add_more'] = can_add_more
        context['max_fingerprints'] = max_fingerprints

        return context


class StudentUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = StudentModel
    permission_required = 'student.change_studentmodel'
    form_class = StudentForm
    template_name = 'student/student/edit.html'

    def get_success_url(self):
        messages.success(self.request, "Student details updated successfully.")
        return reverse('student_detail', kwargs={'pk': self.object.pk})


class StudentDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = StudentModel
    permission_required = 'student.delete_studentmodel'
    template_name = 'student/student/delete.html'
    context_object_name = "student"

    def get_success_url(self):
        messages.success(self.request, "Student deleted successfully.")
        return reverse('student_index')


# -------------------------
# Student Status Actions
# -------------------------
@login_required
@permission_required("student.change_studentmodel", raise_exception=True)
def change_student_status(request, pk, status):
    student = get_object_or_404(StudentModel, pk=pk)

    # Validate the status
    valid_statuses = [choice[0] for choice in StudentModel.Status.choices]
    if status not in valid_statuses:
        messages.error(request, "Invalid status provided.")
        return redirect('student_detail', pk=pk)

    student.status = status
    student.save()
    messages.success(request, f"Status for '{student}' has been updated to {student.get_status_display()}.")
    return redirect('student_detail', pk=pk)


# -------------------------
# Class List Export Views
# -------------------------
@login_required
@permission_required("student.view_studentmodel", raise_exception=True)
def select_class_for_export_view(request):
    context = {
        'class_list': ClassesModel.objects.all().order_by('name'),
        'section_list': ClassSectionModel.objects.all().order_by('name'),
    }
    return render(request, 'student/student/select_class_for_export.html', context)


@login_required
@permission_required("student.view_studentmodel", raise_exception=True)
def export_class_list_view(request):
    class_id = request.GET.get('student_class')
    section_id = request.GET.get('class_section')

    if not class_id or not section_id:
        messages.error(request, "Please select both a class and a section.")
        return redirect('select_class_for_export')

    student_class = get_object_or_404(ClassesModel, pk=class_id)
    class_section = get_object_or_404(ClassSectionModel, pk=section_id)

    student_list = StudentModel.objects.filter(
        student_class=student_class,
        class_section=class_section
    ).select_related('parent').order_by('last_name', 'first_name')

    if not student_list.exists():
        messages.warning(request, "No students found in the selected class and section to export.")
        return redirect('select_class_for_export')

    output = io.BytesIO()
    workbook = Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet(f"{student_class.name} {class_section.name}")

    headers = ['Reg. Number', 'First Name', 'Last Name', 'Parent Name', 'Parent Mobile', 'Parent Email']
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header)

    for row_num, student in enumerate(student_list, 1):
        parent = student.parent
        worksheet.write(row_num, 0, student.registration_number)
        worksheet.write(row_num, 1, student.first_name)
        worksheet.write(row_num, 2, student.last_name)
        worksheet.write(row_num, 3, f"{parent.first_name} {parent.last_name}")
        worksheet.write(row_num, 4, parent.mobile)
        worksheet.write(row_num, 5, parent.email)

    workbook.close()
    output.seek(0)

    filename = f"{student_class.name}-{class_section.name}-Student-List.xlsx"
    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f"attachment; filename={filename}"
    return response


class SelectParentView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    Renders the initial page for a user to search for a parent.
    All data loading is now handled asynchronously by ParentSearchView.
    """
    permission_required = 'student.add_studentmodel'
    template_name = 'student/student/select_parent.html'


class ParentSearchView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    An API endpoint that returns a JSON list of parents matching a search query.
    This is called by JavaScript from the SelectParentView template.
    """
    permission_required = 'student.view_parentmodel'

    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()

        if len(query) < 2:
            # Don't search if the query is too short
            return JsonResponse([], safe=False)

        # Build a query that searches across multiple fields
        # Q objects allow for complex "OR" queries
        search_query = (
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(parent_id__icontains=query) |
                Q(mobile__icontains=query)
        )

        # Find matching parents, limit the results for performance, and select related user data
        parents = ParentModel.objects.filter(search_query).order_by('first_name', 'last_name')[:10]

        # Serialize only the necessary data
        parents_data = [
            {
                'pk': parent.pk,
                'full_name': str(parent),
                'parent_id': parent.parent_id,
                'mobile': parent.mobile,
                'email': parent.email,
            }
            for parent in parents
        ]

        return JsonResponse(parents_data, safe=False)


class GetClassSectionsView(LoginRequiredMixin, View):
    """
    An API endpoint to get the sections associated with a specific class.
    """

    def get(self, request, *args, **kwargs):
        class_id = request.GET.get('class_id')
        if not class_id:
            return JsonResponse({'error': 'Class ID not provided'}, status=400)

        try:
            student_class = ClassesModel.objects.get(pk=class_id)
            sections = student_class.section.all().order_by('name')

            # Serialize the sections into a list of simple objects
            sections_data = [{'id': section.id, 'name': section.name} for section in sections]

            return JsonResponse(sections_data, safe=False)

        except ClassesModel.DoesNotExist:
            return JsonResponse({'error': 'Class not found'}, status=404)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip



@csrf_exempt
@require_POST
def capture_fingerprint(request):
    """
    Capture and store fingerprint for a student
    """
    try:
        # Parse the request data
        data = json.loads(request.body)
        student_id = data.get('student_id')
        finger_name = data.get('finger_name')
        fingerprint_data = data.get('fingerprint_data')
        quality_score = data.get('quality_score', None)

        # Validate required fields
        if not all([student_id, finger_name, fingerprint_data]):
            return JsonResponse({
                'success': False,
                'message': 'Missing required fields: student_id, finger_name, or fingerprint_data'
            }, status=400)

        # Get student
        student = get_object_or_404(StudentModel, id=student_id)

        # Check fingerprint limits
        settings = StudentSettingModel.objects.first()
        max_fingerprints = settings.max_fingerprints_per_student if settings else 2
        current_count = student.fingerprints.filter(is_active=True).count()

        if current_count >= max_fingerprints:
            return JsonResponse({
                'success': False,
                'message': f'Maximum {max_fingerprints} fingerprints allowed per student'
            }, status=400)

        # Check for duplicate finger registration
        if student.fingerprints.filter(finger_name=finger_name, is_active=True).exists():
            return JsonResponse({
                'success': False,
                'message': f'Fingerprint for {finger_name} already registered'
            }, status=400)

        # Validate fingerprint data (basic validation)
        try:
            # Verify it's valid base64
            base64.b64decode(fingerprint_data)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': 'Invalid fingerprint data format'
            }, status=400)

        with transaction.atomic():
            # Create fingerprint record
            fingerprint = FingerprintModel.objects.create(
                student=student,
                finger_name=finger_name,
                fingerprint_template=fingerprint_data,
                quality_score=quality_score,
                capture_device="U.are.U 4500"
            )

            # Update student enrollment status
            student.is_fingerprint_enrolled = True
            if not student.fingerprint_enrollment_date:
                student.fingerprint_enrollment_date = timezone.now()
            student.save(update_fields=['is_fingerprint_enrolled', 'fingerprint_enrollment_date'])

        logger.info(f"Fingerprint captured successfully for student {student.registration_number}")

        return JsonResponse({
            'success': True,
            'message': 'Fingerprint captured and saved successfully',
            'data': {
                'fingerprint_id': fingerprint.id,
                'finger_name': fingerprint.get_finger_name_display(),
                'quality_score': fingerprint.quality_score,
                'created_at': fingerprint.created_at.isoformat()
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)

    except Exception as e:
        logger.error(f"Error capturing fingerprint: {str(e)}", exc_info=True)

        return JsonResponse({
            'success': False,
            'message': 'An error occurred while capturing fingerprint'
        }, status=500)


def simple_template_match(template1: str, template2: str, threshold: float = 0.7) -> tuple[bool, float]:
    """
    Simple template matching for development/testing.
    REPLACE THIS with actual DigitalPersona SDK matching function.
    """
    # This is a placeholder - in production, use the actual SDK
    if template1 == template2:
        return True, 1.0

    # Simple similarity check (NOT suitable for production)
    # You should replace this with proper biometric matching
    similarity = 0.0
    if len(template1) == len(template2):
        matches = sum(c1 == c2 for c1, c2 in zip(template1[:100], template2[:100]))
        similarity = matches / min(100, len(template1))

    return similarity >= threshold, similarity


@csrf_exempt
@require_POST
def identify_student_by_fingerprint(request):
    """
    Identify student by fingerprint scan
    """
    try:
        # Parse request
        data = json.loads(request.body)
        scanned_template = data.get('fingerprint_data')

        if not scanned_template:
            return JsonResponse({
                'success': False,
                'message': 'No fingerprint data provided'
            }, status=400)

        # Validate fingerprint data
        try:
            base64.b64decode(scanned_template)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Invalid fingerprint data format'
            }, status=400)

        # Get matching threshold from settings
        settings = StudentSettingModel.objects.first()
        threshold = settings.fingerprint_match_threshold if settings else 0.7

        best_match = None
        best_score = 0.0

        # Search through all active fingerprints
        active_fingerprints = FingerprintModel.objects.filter(
            is_active=True,
            student__status='active'
        ).select_related('student', 'student__student_wallet', 'student__student_class')

        for fingerprint in active_fingerprints:
            try:
                is_match, score = simple_template_match(
                    scanned_template,
                    fingerprint.fingerprint_template,
                    threshold
                )

                if is_match and score > best_score:
                    best_match = fingerprint
                    best_score = score

            except Exception as e:
                logger.warning(f"Error comparing fingerprint {fingerprint.id}: {e}")
                continue

        if best_match:
            student = best_match.student

            # Mark fingerprint as used
            best_match.mark_used()

            # Get wallet info
            try:
                wallet = student.student_wallet
                wallet_balance = float(wallet.balance)
            except:
                wallet_balance = 0.0

            logger.info(f"Student identified: {student.registration_number} (score: {best_score:.2f})")

            return JsonResponse({
                'success': True,
                'message': 'Student identified successfully',
                'student': {
                    'id': student.id,
                    'name': f"{student.first_name} {student.last_name}",
                    'reg_number': student.registration_number,
                    'student_class': str(student.student_class) if student.student_class else 'Not Assigned',
                    'class_section': str(student.class_section) if student.class_section else '',
                    'status': student.get_status_display(),
                    'wallet_balance': wallet_balance,
                    'image_url': student.image.url if student.image else '',
                    'parent_name': f"{student.parent.first_name} {student.parent.last_name}",
                    'parent_mobile': student.parent.mobile or '',
                },
                'match_details': {
                    'score': round(best_score, 3),
                    'finger_used': best_match.get_finger_name_display(),
                    'last_used': best_match.last_used.isoformat() if best_match.last_used else None,
                }
            })

        else:
            return JsonResponse({
                'success': False,
                'message': 'Fingerprint not recognized. Please try again or contact administrator.'
            }, status=404)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)

    except Exception as e:
        logger.error(f"Error during fingerprint identification: {e}", exc_info=True)

        return JsonResponse({
            'success': False,
            'message': 'An error occurred during identification'
        }, status=500)


@csrf_exempt
@require_POST
def delete_fingerprint(request):
    """
    Delete a specific fingerprint
    """
    try:
        data = json.loads(request.body)
        fingerprint_id = data.get('fingerprint_id')

        fingerprint = get_object_or_404(FingerprintModel, id=fingerprint_id)
        student = fingerprint.student

        # Soft delete - mark as inactive instead of actually deleting
        fingerprint.is_active = False
        fingerprint.save()

        # Update student enrollment status if no active fingerprints remain
        if not student.fingerprints.filter(is_active=True).exists():
            student.is_fingerprint_enrolled = False
            student.save(update_fields=['is_fingerprint_enrolled'])

        return JsonResponse({
            'success': True,
            'message': 'Fingerprint deleted successfully'
        })

    except Exception as e:
        logger.error(f"Error deleting fingerprint: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Error deleting fingerprint'
        }, status=500)


@require_http_methods(["GET"])
def test_scanner_connection(request):
    """
    Test endpoint to check if scanner is connected and working
    """
    return JsonResponse({
        'success': True,
        'message': 'Scanner connection test endpoint ready',
        'instructions': 'Use JavaScript SDK to test actual scanner connection'
    })