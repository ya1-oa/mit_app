from django.apps import AppConfig


class DocsapprConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'docsAppR'
    
    def ready(self):
        import docsAppR.signals