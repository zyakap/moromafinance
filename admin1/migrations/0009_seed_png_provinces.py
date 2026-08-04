"""Seed a Location for each of Papua New Guinea's 22 provinces.

Locations drive the branch/province dropdowns on loans and client profiles, and
the table started empty, so nothing could be assigned a province at all. Each
row is keyed on its province code and created only when missing, so this is safe
to re-run and will not disturb a branch an admin has since renamed or filled in.
"""
from django.db import migrations


#: (province code as stored, readable name). Codes match Location.PROVINCE.
PROVINCES = [
    ('AROB', 'Autonomous Region of Bougainville'),
    ('CENTRAL', 'Central'),
    ('SIMBU', 'Simbu (Chimbu)'),
    ('EHP', 'Eastern Highlands'),
    ('ENB', 'East New Britain'),
    ('EAST SEPIK', 'East Sepik'),
    ('ENGA', 'Enga'),
    ('GULF', 'Gulf'),
    ('HELA', 'Hela'),
    ('JIWAKA', 'Jiwaka'),
    ('MADANG', 'Madang'),
    ('MANUS', 'Manus'),
    ('MILNE BAY', 'Milne Bay'),
    ('MOROBE', 'Morobe'),
    ('NCD', 'National Capital District'),
    ('NEW IRELAND', 'New Ireland'),
    ('ORO', 'Oro (Northern)'),
    ('SHP', 'Southern Highlands'),
    ('WESTERN', 'Western (Fly)'),
    ('WHP', 'Western Highlands'),
    ('WNB', 'West New Britain'),
    ('WEST SEPIK', 'West Sepik (Sandaun)'),
]


def seed_provinces(apps, schema_editor):
    Location = apps.get_model('admin1', 'Location')
    for code, name in PROVINCES:
        Location.objects.get_or_create(province=code, defaults={'name': name})


def unseed_provinces(apps, schema_editor):
    """Remove only the untouched rows this migration added.

    A location that has been renamed, given an address, or has loans or clients
    booked against it is somebody's branch now -- leave it alone.
    """
    Location = apps.get_model('admin1', 'Location')
    for code, name in PROVINCES:
        Location.objects.filter(
            province=code, name=name, address__isnull=True, loans=0, clients=0,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('admin1', '0008_roles_staff_can_borrow_and_gulf_province'),
    ]

    operations = [
        migrations.RunPython(seed_provinces, unseed_provinces),
    ]
