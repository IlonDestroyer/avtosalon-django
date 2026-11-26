from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.CatalogView.as_view(), name="catalog"),
    path("cars/<slug:slug>/", views.CarDetailView.as_view(), name="car_detail"),
    path("cars/<slug:slug>/book/", views.create_booking, name="create_booking"),
    path("cars/<slug:slug>/testdrive/", views.create_testdrive, name="create_testdrive"),
    path("auth/register/", views.register_view, name="register"),
    path("auth/login/", views.UserLoginView.as_view(), name="login"),
    path("auth/logout/", views.UserLogoutView.as_view(), name="logout"),
    path("cabinet/", views.cabinet_view, name="cabinet"),
    path("cars/<slug:slug>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("manager/", views.manager_dashboard, name="manager_dashboard"),
    path("manager/bookings/new/", views.create_customer_booking, name="create_customer_booking"),
    path("cashier/", views.cashier_dashboard, name="cashier_dashboard"),
    path("manager/sales/new/", views.create_sale, name="create_sale"),
    path("manager/sales/<int:sale_id>/status/", views.update_sale_status, name="update_sale_status"),
    path("manager/sales/<int:sale_id>/payment/", views.register_sale_payment, name="register_sale_payment"),
    path("reports/", views.reports_dashboard, name="reports"),
    path("api/", include("cars.api_urls")),
    path("payment/<int:booking_id>/", views.payment_view, name="payment"),
    path("support/", views.support_view, name="support"),
]
