from django.db import migrations, models


def _checar_emails(apps, schema_editor):
    User = apps.get_model('core', 'User')
    vazios = list(User.objects.filter(email='').values_list('username', flat=True))
    if vazios:
        raise RuntimeError(
            'Usuários sem e-mail impedem a migração 0004: '
            + ', '.join(vazios)
            + '. Defina um e-mail para cada um e rode novamente.'
        )
    duplicados = [
        d['email']
        for d in User.objects.values('email').annotate(n=models.Count('id')).filter(n__gt=1)
        if d['email']
    ]
    if duplicados:
        raise RuntimeError(
            'E-mails duplicados impedem a migração 0004: ' + ', '.join(duplicados)
        )


class Migration(migrations.Migration):
    dependencies = [('core', '0003_user_user_papel_cooperativa_coerentes')]
    operations = [
        migrations.RunPython(_checar_emails, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(unique=True, verbose_name='endereço de e-mail'),
        ),
    ]
