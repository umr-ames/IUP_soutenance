from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('healthz/', lambda request: HttpResponse("ok"), name='healthz'),
    path('django-admin/', admin.site.urls),

    path('', include('accounts.urls')),
    path('', include('core.urls')),

    path('student/', include('students.urls')),
    path('professors/', include('professors.urls')),
    path('soutenances/', include('soutenances.urls')),
    path('documents/', include('documents.urls')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
