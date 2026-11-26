from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    Booking, Brand, Car, CarImage, CarModel, Delivery, Favorite,
    Payment, Profile, Sale, SaleService, Service, Supplier, TestDrive,
)


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = "Профиль"


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "vin",
        "year",
        "body",
        "price_kzt",
        "status",
        "mileage_km",
        "created_at",
    )
    list_filter = ("status", "brand", "body", "year", "fuel", "transmission")
    search_fields = ("brand", "model", "trim", "slug", "description", "vin", "stock_number")
    list_editable = ("status",)
    prepopulated_fields = {"slug": ("brand", "model", "trim")}
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": (
                "slug",
                "brand",
                "model",
                "trim",
                "year",
                "body",
                "status",
                "vin",
                "stock_number",
            )
        }),
        ("Характеристики", {
            "fields": (
                "mileage_km",
                "fuel",
                "engine_type",
                "engine_volume",
                "horsepower",
                "transmission",
                "drivetrain",
                "color",
                "car_type",
                "price_kzt",
                "purchase_price_kzt",
                "supplier",
                "arrival_date",
                "storage_location",
            )
        }),
        ("Медиа и описание", {
            "fields": ("image", "image_url", "description")
        }),
        ("Служебное", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "car",
        "user",
        "status",
        "deposit_kzt",
        "expires_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("user__username", "user__email", "car__brand", "car__model")
    list_editable = ("status",)
    raw_id_fields = ("user", "car")
    readonly_fields = ("created_at",)


@admin.register(TestDrive)
class TestDriveAdmin(admin.ModelAdmin):
    list_display = ("id", "car", "user", "status", "scheduled_at", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email", "car__brand", "car__model")
    list_editable = ("status",)
    raw_id_fields = ("user", "car")
    readonly_fields = ("created_at",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "order_no",
        "car",
        "user",
        "amount_kzt",
        "status",
        "method",
        "created_at",
    )
    list_filter = ("status", "method")
    search_fields = ("order_no", "user__username", "user__email")
    list_editable = ("status",)
    raw_id_fields = ("user", "car", "booking")
    readonly_fields = ("order_no", "created_at")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "phone", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email", "full_name", "phone", "iin")


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(CarModel)
class CarModelAdmin(admin.ModelAdmin):
    list_display = ("name", "brand")
    list_filter = ("brand",)
    search_fields = ("name", "brand__name")


@admin.register(CarImage)
class CarImageAdmin(admin.ModelAdmin):
    list_display = ("car", "caption", "position")
    list_filter = ("car__brand",)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "car", "created_at")
    search_fields = ("user__username", "car__vin", "car__brand", "car__model")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "bin", "contact_name", "phone", "email")
    search_fields = ("name", "bin", "contact_name", "phone", "email")


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("supplier", "car", "status", "expected_at", "received_at", "purchase_price_kzt")
    list_filter = ("status", "supplier")
    search_fields = ("car__vin", "car__brand", "car__model", "supplier__name")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "price_kzt", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


class SaleServiceInline(admin.TabularInline):
    model = SaleService
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "car", "manager", "total_kzt", "status", "created_at", "completed_at")
    list_filter = ("status", "payment_method", "created_at")
    search_fields = ("customer__username", "car__vin", "car__brand", "car__model", "manager__username")
    inlines = [SaleServiceInline]
    readonly_fields = ("total_kzt", "created_at", "completed_at")


@admin.register(SaleService)
class SaleServiceAdmin(admin.ModelAdmin):
    list_display = ("sale", "service", "price_kzt", "quantity")
    search_fields = ("sale__car__vin", "service__name")
