# Generated manually — BUG-001 fix

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def set_created_by_from_host(apps, schema_editor):
    Room = apps.get_model('room', 'Room')
    Room.objects.update(created_by=models.F('host'))


class Migration(migrations.Migration):

    dependencies = [
        ('room', '0005_remove_room_members_room_role_configuration_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='room',
            name='created_by',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='created_rooms',
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(
            set_created_by_from_host,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='room',
            name='created_by',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='created_rooms',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
