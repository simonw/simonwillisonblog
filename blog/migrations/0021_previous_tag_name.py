from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0020_tag_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='PreviousTagName',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('previous_name', models.SlugField()),
                ('tag', models.ForeignKey(on_delete=models.CASCADE, to='blog.Tag')),
            ],
        ),
    ]
