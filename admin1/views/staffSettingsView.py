"""Settings → Staff: create, edit and control access for staff accounts.

Single page (mirrors the Banks/Employers settings pattern): a create/edit form
plus the team list with per-row actions. Suspension flips User.suspended on and
User.active off, which blocks login; reactivation reverses both.

Nested under Roles & Access (not a separate settings tab) — this is the UI
path for assigning the Manager role introduced alongside role_manager_enabled.
"""
import logging

from django.contrib import messages
from django.shortcuts import render, redirect

from accounts.functions import admin_check
from accounts.models import User, UserProfile, StaffProfile

logger = logging.getLogger(__name__)

_TYPES = ['STAFF', 'MANAGER', 'ADMIN', 'DIRECTOR']
_CATEGORIES = ['FULL-TIME', 'PART-TIME', 'GRADUATE', 'CONTRACTOR']
_GROUPS = ['WORKER', 'SUPERVISOR', 'MANAGER']


def _staff_rows():
    rows = []
    for sp in StaffProfile.objects.select_related('user', 'user__user').order_by('user__first_name'):
        prof = sp.user
        usr = prof.user
        rows.append({'sp': sp, 'prof': prof, 'usr': usr,
                     'suspended': bool(getattr(usr, 'suspended', False)) or not getattr(usr, 'active', True)})
    return rows


@admin_check
def admin_settings_staff(request):
    edit_sp = None
    if request.GET.get('edit'):
        edit_sp = StaffProfile.objects.filter(pk=request.GET['edit']).select_related('user', 'user__user').first()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_staff':
            email = (request.POST.get('email') or '').strip().lower()
            first = (request.POST.get('first_name') or '').strip()
            last = (request.POST.get('last_name') or '').strip()
            password = request.POST.get('password') or ''
            if not (email and first and last and password):
                messages.error(request, 'Email, first name, last name and password are all required.', extra_tags='danger')
                return redirect('admin_settings_staff')
            if len(password) < 8:
                messages.error(request, 'Password must be at least 8 characters.', extra_tags='danger')
                return redirect('admin_settings_staff')
            if User.objects.filter(email=email).exists():
                messages.error(request, f'A user with email {email} already exists.', extra_tags='danger')
                return redirect('admin_settings_staff')
            usr = User.objects.create_user(email=email, password=password)
            usr.active = True
            usr.staff = True
            usr.confirmed = True
            usr.save()
            prof = UserProfile.objects.create(
                user=usr, first_name=first, last_name=last, email=email,
                category='STAFF', activation=1,
                mobile1=(request.POST.get('mobile') or None),
            )
            StaffProfile.objects.create(
                user=prof,
                position=(request.POST.get('position') or '').strip() or None,
                type_of_staff=(request.POST.get('type_of_staff') if request.POST.get('type_of_staff') in _TYPES else 'STAFF'),
                category=(request.POST.get('staff_category') if request.POST.get('staff_category') in _CATEGORIES else 'FULL-TIME'),
                position_group=(request.POST.get('position_group') if request.POST.get('position_group') in _GROUPS else 'WORKER'),
            )
            logger.info('STAFF-CREATE %s by %s', email, request.user.email)
            messages.success(request, f'Staff account for {first} {last} ({email}) created.', extra_tags='info')
            return redirect('admin_settings_staff')

        sp = StaffProfile.objects.filter(pk=request.POST.get('staff_id')).select_related('user', 'user__user').first()
        if not sp:
            messages.error(request, 'Staff member not found.', extra_tags='danger')
            return redirect('admin_settings_staff')
        prof, usr = sp.user, sp.user.user

        if action == 'update_staff':
            prof.first_name = (request.POST.get('first_name') or prof.first_name).strip()
            prof.last_name = (request.POST.get('last_name') or prof.last_name).strip()
            if request.POST.get('mobile'):
                prof.mobile1 = request.POST.get('mobile')
            prof.save()
            sp.position = (request.POST.get('position') or '').strip() or sp.position
            if request.POST.get('type_of_staff') in _TYPES:
                sp.type_of_staff = request.POST['type_of_staff']
            if request.POST.get('staff_category') in _CATEGORIES:
                sp.category = request.POST['staff_category']
            if request.POST.get('position_group') in _GROUPS:
                sp.position_group = request.POST['position_group']
            sp.save()
            logger.info('STAFF-UPDATE %s by %s', usr.email, request.user.email)
            messages.success(request, f'{prof.first_name} {prof.last_name} updated.', extra_tags='info')
            return redirect('admin_settings_staff')

        if action == 'toggle_suspend':
            if usr.pk == request.user.pk:
                messages.error(request, 'You cannot suspend your own account.', extra_tags='danger')
                return redirect('admin_settings_staff')
            suspending = not (usr.suspended or not usr.active)
            usr.suspended = suspending
            usr.active = not suspending
            usr.save(update_fields=['suspended', 'active'])
            logger.info('STAFF-%s %s by %s', 'SUSPEND' if suspending else 'REACTIVATE', usr.email, request.user.email)
            messages.success(request,
                             f'{prof.first_name} {prof.last_name} {"suspended — login blocked" if suspending else "reactivated"}.',
                             extra_tags='info')
            return redirect('admin_settings_staff')

        if action == 'reset_password':
            pw = request.POST.get('new_password') or ''
            if len(pw) < 8:
                messages.error(request, 'New password must be at least 8 characters.', extra_tags='danger')
                return redirect('admin_settings_staff')
            usr.set_password(pw)
            usr.save()
            logger.info('STAFF-PASSWORD-RESET %s by %s', usr.email, request.user.email)
            messages.success(request, f'Password reset for {prof.first_name} {prof.last_name}.', extra_tags='info')
            return redirect('admin_settings_staff')

        messages.error(request, 'Unknown action.', extra_tags='danger')
        return redirect('admin_settings_staff')

    return render(request, 'settings_staff.html', {
        'nav': 'admin_settings_roles',
        'rows': _staff_rows(),
        'edit_sp': edit_sp,
        'types': _TYPES, 'categories': _CATEGORIES, 'groups': _GROUPS,
    })
