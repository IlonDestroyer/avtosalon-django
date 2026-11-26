from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cars.models import Booking, Car


class Command(BaseCommand):
    help = "Помечает просроченные брони и освобождает автомобили без активной брони."

    def handle(self, *args, **options):
        now = timezone.now()
        expired_count = 0
        with transaction.atomic():
            bookings = list(
                Booking.objects.select_for_update().filter(
                    status__in=(Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED),
                    expires_at__lte=now,
                )
            )
            car_ids = {booking.car_id for booking in bookings}
            for booking in bookings:
                booking.status = Booking.STATUS_EXPIRED
                booking.save(update_fields=["status"])
                expired_count += 1
            for car in Car.objects.select_for_update().filter(
                pk__in=car_ids,
                status=Car.STATUS_BOOKED,
            ):
                if not Booking.objects.filter(
                    car=car,
                    status__in=(Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED),
                    expires_at__gt=now,
                ).exists():
                    car.status = Car.STATUS_AVAILABLE
                    car.save(update_fields=["status"])
        self.stdout.write(self.style.SUCCESS(f"Просрочено броней: {expired_count}"))
