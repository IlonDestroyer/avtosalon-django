from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.management import call_command

from .models import Booking, Car, Favorite, Payment, Profile, Sale, SaleService, Service, TestDrive


class DealershipWorkflowTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(username="client", password="Strong-pass-123")
        self.staff_user = User.objects.create_user(username="manager", password="Strong-pass-123")
        self.staff_user.profile.role = Profile.ROLE_MANAGER
        self.staff_user.profile.save()
        self.car = Car.objects.create(
            brand="Toyota", model="Camry", year=2025, price_kzt=18_000_000,
            vin="JTNB11HK0K3000001",
        )

    def test_booking_reserves_available_car(self):
        self.client.login(username="client", password="Strong-pass-123")
        response = self.client.post(reverse("create_booking", args=[self.car.slug]))
        self.assertRedirects(response, reverse("payment", args=[1]))
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, Car.STATUS_BOOKED)
        self.assertEqual(Booking.objects.get().user, self.client_user)

    def test_overlapping_test_drive_is_rejected(self):
        scheduled = timezone.now() + timedelta(days=2)
        TestDrive.objects.create(user=self.client_user, car=self.car, scheduled_at=scheduled)
        self.client.login(username="manager", password="Strong-pass-123")
        response = self.client.post(
            reverse("create_testdrive", args=[self.car.slug]),
            {"scheduled_at": timezone.localtime(scheduled + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")},
        )
        self.assertRedirects(response, reverse("car_detail", args=[self.car.slug]))
        self.assertEqual(TestDrive.objects.count(), 1)

    def test_completed_sale_includes_services_and_marks_car_sold(self):
        service = Service.objects.create(name="Страхование", price_kzt=300_000)
        sale = Sale.objects.create(
            customer=self.client_user, manager=self.staff_user, car=self.car,
            car_price_kzt=18_000_000, discount_kzt=400_000,
        )
        SaleService.objects.create(sale=sale, service=service, price_kzt=300_000)
        sale.status = Sale.STATUS_COMPLETED
        sale.save()
        sale.refresh_from_db()
        self.car.refresh_from_db()
        self.assertEqual(sale.total_kzt, 17_900_000)
        self.assertEqual(self.car.status, Car.STATUS_SOLD)
        self.assertIsNotNone(self.car.sold_at)

    def test_favorites_are_private_to_their_owner(self):
        Favorite.objects.create(user=self.client_user, car=self.car)
        self.client.login(username="manager", password="Strong-pass-123")
        response = self.client.get("/api/favorites/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_role_gates_manager_and_director_pages(self):
        self.client.login(username="client", password="Strong-pass-123")
        self.assertEqual(self.client.get(reverse("manager_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports")).status_code, 403)

    def test_catalog_search_matches_vin(self):
        response = self.client.get(reverse("catalog"), {"search": "JTNB11HK0K3000001"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Toyota Camry")

    def test_api_booking_uses_authenticated_customer_and_reserves_car(self):
        self.client.login(username="client", password="Strong-pass-123")
        response = self.client.post("/api/bookings/", {"car": self.car.pk}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.get().user, self.client_user)
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, Car.STATUS_BOOKED)

    def test_manager_can_complete_sale_with_service_and_discount(self):
        service = Service.objects.create(name="Страхование", price_kzt=300_000)
        self.client.login(username="manager", password="Strong-pass-123")
        response = self.client.post(
            reverse("create_sale"),
            {
                "customer": self.client_user.pk,
                "car": self.car.pk,
                "services": [service.pk],
                "discount_kzt": 400_000,
                "payment_method": Sale.METHOD_CASH,
                "complete": "on",
            },
        )
        self.assertRedirects(response, reverse("manager_dashboard"))
        sale = Sale.objects.get()
        self.assertEqual(sale.total_kzt, 17_900_000)
        self.assertEqual(sale.status, Sale.STATUS_COMPLETED)
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, Car.STATUS_SOLD)

    def test_manager_can_reserve_for_customer_and_complete_draft_sale(self):
        self.client.login(username="manager", password="Strong-pass-123")
        response = self.client.post(
            reverse("create_customer_booking"),
            {"customer": self.client_user.pk, "car": self.car.pk, "comment": "Связаться вечером"},
        )
        self.assertRedirects(response, reverse("manager_dashboard"))
        booking = Booking.objects.get()
        self.assertEqual(booking.user, self.client_user)
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, Car.STATUS_BOOKED)
        booking.status = Booking.STATUS_CANCELLED
        booking.save(update_fields=["status"])
        self.car.status = Car.STATUS_AVAILABLE
        self.car.save(update_fields=["status"])
        self.client.post(
            reverse("create_sale"),
            {"customer": self.client_user.pk, "car": self.car.pk, "discount_kzt": "0"},
        )
        sale = Sale.objects.get()
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, Car.STATUS_PREPARING)
        self.client.post(reverse("update_sale_status", args=[sale.pk]), {"status": Sale.STATUS_COMPLETED})
        sale.refresh_from_db()
        self.car.refresh_from_db()
        self.assertEqual(sale.status, Sale.STATUS_COMPLETED)
        self.assertEqual(self.car.status, Car.STATUS_SOLD)

    def test_cashier_can_register_payment_and_returns_to_cashier_dashboard(self):
        cashier = User.objects.create_user(username="cashier", password="Strong-pass-123")
        cashier.profile.role = Profile.ROLE_CASHIER
        cashier.profile.save()
        sale = Sale.objects.create(
            customer=self.client_user, manager=self.staff_user, car=self.car,
            car_price_kzt=self.car.price_kzt, status=Sale.STATUS_COMPLETED,
        )
        self.client.login(username="cashier", password="Strong-pass-123")
        response = self.client.post(
            reverse("register_sale_payment", args=[sale.pk]),
            {"amount_kzt": "1000000", "method": Payment.METHOD_TRANSFER},
        )
        self.assertRedirects(response, reverse("cashier_dashboard"))
        self.assertEqual(Payment.objects.filter(sale=sale).count(), 1)

    def test_client_cannot_access_another_users_favorite(self):
        other = User.objects.create_user(username="other", password="Strong-pass-123")
        favorite = Favorite.objects.create(user=other, car=self.car)
        self.client.login(username="client", password="Strong-pass-123")
        response = self.client.delete(f"/api/favorites/{favorite.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Favorite.objects.filter(pk=favorite.pk).exists())

    def test_staff_workspaces_render_for_their_roles(self):
        self.client.login(username="manager", password="Strong-pass-123")
        self.assertEqual(self.client.get(reverse("manager_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("create_sale")).status_code, 200)
        cashier = User.objects.create_user(username="cashier", password="Strong-pass-123")
        cashier.profile.role = Profile.ROLE_CASHIER
        cashier.profile.save()
        self.client.login(username="cashier", password="Strong-pass-123")
        self.assertEqual(self.client.get(reverse("cashier_dashboard")).status_code, 200)
        director = User.objects.create_user(username="director", password="Strong-pass-123")
        director.profile.role = Profile.ROLE_DIRECTOR
        director.profile.save()
        self.client.login(username="director", password="Strong-pass-123")
        self.assertEqual(self.client.get(reverse("reports")).status_code, 200)

    def test_client_profile_validates_iin(self):
        self.client.login(username="client", password="Strong-pass-123")
        response = self.client.post(
            reverse("cabinet"),
            {"full_name": "Клиент", "phone": "+77001234567", "address": "Алматы", "iin": "123"},
        )
        self.assertEqual(response.status_code, 200)
        self.client_user.profile.refresh_from_db()
        self.assertEqual(self.client_user.profile.iin, "")

    def test_administrator_role_grants_and_revokes_admin_panel_access(self):
        administrator = User.objects.create_user(username="administrator", password="Strong-pass-123")
        administrator.profile.role = Profile.ROLE_ADMIN
        administrator.profile.save()
        self.assertTrue(administrator.is_staff)
        self.client.login(username="administrator", password="Strong-pass-123")
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        administrator.profile.role = Profile.ROLE_CLIENT
        administrator.profile.save()
        administrator.refresh_from_db()
        self.assertFalse(administrator.is_staff)

    def test_expire_bookings_command_releases_car(self):
        booking = Booking.objects.create(
            user=self.client_user, car=self.car, expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.car.status = Car.STATUS_BOOKED
        self.car.save(update_fields=["status"])
        call_command("expire_bookings")
        booking.refresh_from_db()
        self.car.refresh_from_db()
        self.assertEqual(booking.status, Booking.STATUS_EXPIRED)
        self.assertEqual(self.car.status, Car.STATUS_AVAILABLE)

    def test_cashier_cannot_overpay_sale(self):
        cashier = User.objects.create_user(username="cashier", password="Strong-pass-123")
        cashier.profile.role = Profile.ROLE_CASHIER
        cashier.profile.save()
        sale = Sale.objects.create(
            customer=self.client_user, manager=self.staff_user, car=self.car,
            car_price_kzt=self.car.price_kzt, status=Sale.STATUS_COMPLETED,
        )
        self.client.login(username="cashier", password="Strong-pass-123")
        self.client.post(
            reverse("register_sale_payment", args=[sale.pk]),
            {"amount_kzt": str(sale.total_kzt + 1), "method": Payment.METHOD_TRANSFER},
        )
        self.assertFalse(Payment.objects.filter(sale=sale).exists())
