from django.urls import path
from . import views
from .views import ItemsView

urlpatterns = [
    path('', views.home, name='home'),  # URL route for the home view
    path('api/generate_route/', ItemsView.as_view(), name='items-list'),
]