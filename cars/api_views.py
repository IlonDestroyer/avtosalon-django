from rest_framework import permissions, viewsets
from rest_framework.exceptions import ValidationError

from .models import Booking, Car, Favorite, Profile, Sale, TestDrive
from .serializers import BookingSerializer, CarSerializer, FavoriteSerializer, SaleSerializer, TestDriveSerializer


class CarViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CarSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        queryset = Car.objects.exclude(status=Car.STATUS_UNLISTED)
        params = self.request.query_params
        for key in ("brand", "model", "body", "fuel", "transmission", "drivetrain", "color", "status", "car_type"):
            if params.get(key):
                queryset = queryset.filter(**{f"{key}__icontains": params[key]} if key in ("brand", "model") else {key: params[key]})
        if params.get("search"):
            from django.db.models import Q
            term = params["search"]
            queryset = queryset.filter(Q(brand__icontains=term) | Q(model__icontains=term) | Q(vin__icontains=term) | Q(stock_number__icontains=term))
        for param, lookup in (("price_min", "price_kzt__gte"), ("price_max", "price_kzt__lte"), ("year", "year"), ("mileage_max", "mileage_km__lte")):
            if params.get(param):
                try:
                    value = int(params[param])
                    if value < 0:
                        raise ValueError
                except ValueError:
                    raise ValidationError({param: "Укажите неотрицательное целое число."})
                queryset = queryset.filter(**{lookup: value})
        ordering = params.get("sort")
        valid_orderings = {"price_asc": "price_kzt", "price_desc": "-price_kzt", "year": "-year", "newest": "-created_at"}
        return queryset.order_by(valid_orderings.get(ordering, "-created_at"))


class OwnedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


class BookingViewSet(OwnedModelViewSet):
    serializer_class = BookingSerializer
    queryset = Booking.objects.all()
    http_method_names = ["get", "post", "head", "options"]


class TestDriveViewSet(OwnedModelViewSet):
    serializer_class = TestDriveSerializer
    queryset = TestDrive.objects.all()
    http_method_names = ["get", "post", "head", "options"]


class FavoriteViewSet(OwnedModelViewSet):
    serializer_class = FavoriteSerializer
    queryset = Favorite.objects.all()
    http_method_names = ["get", "post", "delete", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class StaffSalesViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        profile = getattr(self.request.user, "profile", None)
        allowed = self.request.user.is_superuser or (
            profile and profile.role in (Profile.ROLE_MANAGER, Profile.ROLE_ADMIN, Profile.ROLE_DIRECTOR)
        )
        return Sale.objects.all() if allowed else Sale.objects.none()
