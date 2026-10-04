from django.contrib import admin
from django.urls import path
from content import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/projects/', views.projects),
    path('api/rates/', views.rates),
    path('api/documents/', views.documents),
    path('api/documents/<uuid:document_id>/', views.document, name='content_document'),
    path('api/images/<uuid:image_id>/', views.image, name='content_image'),
    path('healthz/', views.health),
]
