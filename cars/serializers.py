from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Booking, Car, CarImage, Favorite, Sale, TestDrive


class CarImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarImage
        fields = ("id", "image", "caption", "position")


class CarSerializer(serializers.ModelSerializer):
    title = serializers.CharField(read_only=True)
    images = CarImageSerializer(many=True, read_only=True)

    class Meta:
        model = Car
        fields = (
            "id", "slug", "title", "brand", "model", "trim", "stock_number", "vin",
            "year", "body", "engine_type", "engine_volume", "fuel", "horsepower",
            "transmission", "drivetrain", "color", "mileage_km", "car_type",
            "price_kzt", "description", "status", "image_url", "images",
        )


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ("id", "car", "status", "deposit_kzt", "expires_at", "comment", "created_at")
        read_only_fields = ("status", "deposit_kzt", "expires_at", "created_at")

    def validate_car(self, car):
        if car.status != Car.STATUS_AVAILABLE:
            raise serializers.ValidationError("Автомобиль недоступен для бронирования.")
        return car

    def create(self, validated_data):
        with transaction.atomic():
            car = Car.objects.select_for_update().get(pk=validated_data["car"].pk)
            active = Booking.objects.filter(
                car=car,
                status__in=(Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED),
                expires_at__gt=timezone.now(),
            ).exists()
            if car.status != Car.STATUS_AVAILABLE or active:
                raise serializers.ValidationError({"car": "Автомобиль уже забронирован."})
            booking = Booking.objects.create(
                **validated_data, user=self.context["request"].user,
                deposit_kzt=500_000, expires_at=timezone.now() + timedelta(days=3),
            )
            car.status = Car.STATUS_BOOKED
            car.save(update_fields=["status"])
            return booking


class TestDriveSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestDrive
        fields = ("id", "car", "status", "scheduled_at", "created_at")
        read_only_fields = ("status", "created_at")

    def validate(self, attrs):
        scheduled = attrs["scheduled_at"]
        if scheduled <= timezone.now():
            raise serializers.ValidationError({"scheduled_at": "Дата должна быть в будущем."})
        if attrs["car"].status in (Car.STATUS_SOLD, Car.STATUS_UNLISTED):
            raise serializers.ValidationError({"car": "Автомобиль недоступен для тест-драйва."})
        conflict = TestDrive.objects.filter(
            car=attrs["car"],
            scheduled_at__lt=scheduled + timedelta(hours=1),
            scheduled_at__gt=scheduled - timedelta(hours=1),
            status__in=(TestDrive.STATUS_PLANNED, TestDrive.STATUS_CONFIRMED),
        ).exists()
        if conflict:
            raise serializers.ValidationError({"scheduled_at": "Время пересекается с другой записью."})
        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            car = Car.objects.select_for_update().get(pk=validated_data["car"].pk)
            scheduled = validated_data["scheduled_at"]
            conflict = TestDrive.objects.filter(
                car=car,
                scheduled_at__lt=scheduled + timedelta(hours=1),
                scheduled_at__gt=scheduled - timedelta(hours=1),
                status__in=(TestDrive.STATUS_PLANNED, TestDrive.STATUS_CONFIRMED),
            ).exists()
            if conflict:
                raise serializers.ValidationError({"scheduled_at": "Время пересекается с другой записью."})
            validated_data["user"] = self.context["request"].user
            validated_data["car"] = car
            return super().create(validated_data)


class FavoriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Favorite
        fields = ("id", "car", "created_at")
        read_only_fields = ("created_at",)


class SaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sale
        fields = (
            "id", "customer", "car", "manager", "car_price_kzt",
            "discount_kzt", "total_kzt", "payment_method", "status",
            "created_at", "completed_at",
        )
        read_only_fields = ("manager", "total_kzt", "created_at", "completed_at")
