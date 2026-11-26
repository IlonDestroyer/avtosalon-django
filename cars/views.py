from datetime import date, timedelta
from functools import wraps
import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, F, Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, ListView

from .forms import (
    BookingForm,
    CarFilterForm,
    LoginForm,
    PaymentForm,
    ProfileUpdateForm,
    RegisterForm,
    TestDriveForm,
)
from .models import Booking, Car, Favorite, Payment, Profile, Sale, SaleService, Service, TestDrive

logger = logging.getLogger(__name__)


def roles_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            profile = getattr(request.user, "profile", None)
            if request.user.is_superuser or (profile and profile.role in roles):
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden("Недостаточно прав для выполнения операции.")
        return wrapped
    return decorator


class CatalogView(ListView):
    model = Car
    template_name = "cars/catalog.html"
    context_object_name = "cars"
    paginate_by = 12

    def get_queryset(self):
        qs = Car.objects.exclude(status=Car.STATUS_UNLISTED)
        form = self.get_filter_form()
        if form.is_valid():
            data = form.cleaned_data
            search = data.get("search")
            if search:
                qs = qs.filter(
                    Q(brand__icontains=search)
                    | Q(model__icontains=search)
                    | Q(trim__icontains=search)
                    | Q(body__icontains=search)
                    | Q(description__icontains=search)
                    | Q(vin__icontains=search)
                    | Q(stock_number__icontains=search)
                )
            brand = data.get("brand")
            if brand:
                qs = qs.filter(brand=brand)
            body = data.get("body")
            if body:
                qs = qs.filter(body=body)
            year = data.get("year")
            if year:
                qs = qs.filter(year=year)
            for key, field in (
                ("fuel", "fuel"),
                ("transmission", "transmission"),
                ("drivetrain", "drivetrain"),
                ("color", "color"),
                ("status", "status"),
                ("car_type", "car_type"),
            ):
                if self.request.GET.get(key):
                    qs = qs.filter(**{field: self.request.GET[key]})
            if self.request.GET.get("model"):
                qs = qs.filter(model__icontains=self.request.GET["model"])
            price_from = data.get("price_from")
            if price_from is not None:
                qs = qs.filter(price_kzt__gte=price_from * 1_000_000)
            price_to = data.get("price_to")
            if price_to is not None:
                qs = qs.filter(price_kzt__lte=price_to * 1_000_000)
        mileage_max = self.request.GET.get("mileage_max")
        if mileage_max and mileage_max.isdigit():
            qs = qs.filter(mileage_km__lte=int(mileage_max))
        sort = self.request.GET.get("sort")
        ordering = {
            "price_asc": "price_kzt",
            "price_desc": "-price_kzt",
            "year": "-year",
            "newest": "-created_at",
        }.get(sort, "-created_at")
        return qs.select_related("brand_catalog", "model_catalog").order_by(ordering)

    def get_filter_form(self):
        brands = Car.objects.values_list("brand", flat=True).distinct().order_by("brand")
        years = Car.objects.values_list("year", flat=True).distinct().order_by("-year")
        return CarFilterForm(self.request.GET or None, brands=brands, years=years)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self.get_filter_form()
        ctx["available_count"] = Car.objects.filter(status=Car.STATUS_AVAILABLE).count()
        ctx["favorite_ids"] = set(Favorite.objects.filter(user=self.request.user).values_list("car_id", flat=True)) if self.request.user.is_authenticated else set()
        ctx["filter_status_choices"] = Car.STATUS_CHOICES
        return ctx


class CarDetailView(DetailView):
    model = Car
    template_name = "cars/car_detail.html"
    context_object_name = "car"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["booking_form"] = BookingForm()
        ctx["testdrive_form"] = TestDriveForm()
        ctx["is_favorite"] = self.request.user.is_authenticated and Favorite.objects.filter(user=self.request.user, car=self.object).exists()
        ctx["car_images"] = self.object.images.all()
        return ctx


def register_view(request):
    if request.user.is_authenticated:
        return redirect("catalog")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Регистрация успешна. Добро пожаловать!")
            return redirect("catalog")
    else:
        form = RegisterForm()
    return render(request, "cars/auth.html", {"form": form, "mode": "register"})


class UserLoginView(LoginView):
    template_name = "cars/auth.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["mode"] = "login"
        return ctx


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("catalog")


@login_required
def create_booking(request, slug):
    car = get_object_or_404(Car, slug=slug)
    if request.method != "POST":
        return redirect("car_detail", slug=slug)

    form = BookingForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Проверьте данные формы.")
        return redirect("car_detail", slug=slug)

    try:
        with transaction.atomic():
            car = Car.objects.select_for_update().get(pk=car.pk)
            now = timezone.now()
            Booking.objects.filter(
                car=car,
                status__in=[Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED],
                expires_at__lte=now,
            ).update(status=Booking.STATUS_EXPIRED)
            active = Booking.objects.filter(
                car=car,
                status__in=[Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED],
                expires_at__gt=now,
            ).exists()
            if car.status == Car.STATUS_BOOKED and not active:
                car.status = Car.STATUS_AVAILABLE
                car.save(update_fields=["status"])
            if active or car.status != Car.STATUS_AVAILABLE:
                messages.error(request, "Этот автомобиль недоступен для бронирования.")
                return redirect("car_detail", slug=slug)
            booking = form.save(commit=False)
            booking.user = request.user
            booking.car = car
            booking.deposit_kzt = 500_000
            booking.expires_at = timezone.now() + timedelta(days=3)
            booking.status = Booking.STATUS_CREATED
            booking.save()
            car.status = Car.STATUS_BOOKED
            car.save(update_fields=["status"])
            logger.info("Booking created: booking_id=%s car_id=%s user_id=%s", booking.pk, car.pk, request.user.pk)
    except IntegrityError:
        messages.error(request, "Не удалось создать бронь: автомобиль уже занят.")
        return redirect("car_detail", slug=slug)

    messages.success(request, "Автомобиль забронирован на 3 дня.")
    return redirect("payment", booking_id=booking.pk)


@login_required
def create_testdrive(request, slug):
    car = get_object_or_404(Car, slug=slug)
    if car.status in (Car.STATUS_SOLD, Car.STATUS_UNLISTED, Car.STATUS_IN_TRANSIT, Car.STATUS_SERVICE):
        messages.error(request, "Этот автомобиль недоступен для тест-драйва.")
        return redirect("car_detail", slug=slug)

    if request.method != "POST":
        return redirect("car_detail", slug=slug)

    form = TestDriveForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Укажите дату и время тест-драйва.")
        return redirect("car_detail", slug=slug)

    scheduled = form.cleaned_data["scheduled_at"]
    if scheduled <= timezone.now():
        messages.error(request, "Дата тест-драйва должна быть в будущем.")
        return redirect("car_detail", slug=slug)

    with transaction.atomic():
        car = Car.objects.select_for_update().get(pk=car.pk)
        conflict = TestDrive.objects.filter(
            car=car,
            scheduled_at__lt=scheduled + timedelta(hours=1),
            scheduled_at__gt=scheduled - timedelta(hours=1),
            status__in=[TestDrive.STATUS_PLANNED, TestDrive.STATUS_CONFIRMED],
        ).exists()
        if conflict:
            messages.error(request, "Этот временной интервал уже занят. Выберите другое время.")
            return redirect("car_detail", slug=slug)
        td = form.save(commit=False)
        td.user = request.user
        td.car = car
        td.status = TestDrive.STATUS_PLANNED
        td.save()
        logger.info("Test drive scheduled: test_drive_id=%s car_id=%s user_id=%s", td.pk, car.pk, request.user.pk)

    messages.success(request, "Вы записаны на тест-драйв.")
    return redirect("cabinet")


@login_required
def payment_view(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    if (
        booking.status in (Booking.STATUS_COMPLETED, Booking.STATUS_CANCELLED, Booking.STATUS_EXPIRED)
        or booking.expires_at <= timezone.now()
        or booking.payments.filter(status=Payment.STATUS_PAID).exists()
    ):
        messages.info(request, "Эту бронь больше нельзя оплатить.")
        return redirect("cabinet")

    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                booking = Booking.objects.select_for_update().get(pk=booking.pk)
                if (
                    booking.status in (Booking.STATUS_COMPLETED, Booking.STATUS_CANCELLED, Booking.STATUS_EXPIRED)
                    or booking.expires_at <= timezone.now()
                    or booking.payments.filter(status=Payment.STATUS_PAID).exists()
                ):
                    messages.info(request, "Платёж по этой брони уже зарегистрирован.")
                    return redirect("cabinet")
                payment = Payment.objects.create(
                    user=request.user,
                    car=booking.car,
                    booking=booking,
                    amount_kzt=booking.deposit_kzt,
                    status=Payment.STATUS_PAID,
                    method=form.cleaned_data["method"],
                )
                booking.status = Booking.STATUS_CONFIRMED
                booking.save(update_fields=["status"])
            logger.info("Booking payment recorded: payment_id=%s booking_id=%s", payment.pk, booking.pk)
            messages.success(
                request,
                f"Оплата прошла успешно. Заказ {payment.order_no}.",
            )
            return redirect("cabinet")
    else:
        form = PaymentForm()

    return render(
        request,
        "cars/payment.html",
        {"booking": booking, "form": form},
    )


@login_required
def cabinet_view(request):
    profile = getattr(request.user, "profile", None)
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Профиль обновлён.")
            return redirect("cabinet")
    else:
        form = ProfileUpdateForm(instance=profile)
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related("car")
        .order_by("-created_at")
    )
    drives = (
        TestDrive.objects.filter(user=request.user)
        .select_related("car")
        .order_by("scheduled_at")
    )
    payments = (
        Payment.objects.filter(user=request.user)
        .select_related("car")
        .order_by("-created_at")
    )
    favorites = Favorite.objects.filter(user=request.user).select_related("car")
    sales = Sale.objects.filter(customer=request.user, status=Sale.STATUS_COMPLETED).select_related("car")
    return render(
        request,
        "cars/cabinet.html",
        {
            "profile": profile,
            "bookings": bookings,
            "drives": drives,
            "payments": payments,
            "favorites": favorites,
            "sales": sales,
            "profile_form": form,
        },
    )


def support_view(request):
    return render(request, "cars/support.html")


@login_required
def toggle_favorite(request, slug):
    if request.method != "POST":
        return redirect("car_detail", slug=slug)
    car = get_object_or_404(Car, slug=slug)
    favorite, created = Favorite.objects.get_or_create(user=request.user, car=car)
    if not created:
        favorite.delete()
    return redirect("car_detail", slug=slug)


@roles_required(Profile.ROLE_MANAGER, Profile.ROLE_ADMIN)
def manager_dashboard(request):
    today = timezone.localdate()
    context = {
        "new_clients": request.user.__class__.objects.filter(date_joined__date=today, profile__role=Profile.ROLE_CLIENT).count(),
        "bookings": Booking.objects.filter(status__in=[Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED]).select_related("car", "user").order_by("-created_at")[:10],
        "drives": TestDrive.objects.filter(scheduled_at__date=today).select_related("car", "user").order_by("scheduled_at"),
        "available_cars": Car.objects.filter(status=Car.STATUS_AVAILABLE).count(),
        "sales": Sale.objects.filter(status=Sale.STATUS_DRAFT).select_related("car", "customer").order_by("-created_at")[:10],
        "customers": request.user.__class__.objects.filter(is_staff=False).select_related("profile").order_by("-date_joined")[:10],
        "booking_cars": Car.objects.filter(status=Car.STATUS_AVAILABLE).order_by("brand", "model"),
        "booking_customers": request.user.__class__.objects.filter(is_staff=False, profile__role=Profile.ROLE_CLIENT).order_by("username"),
    }
    return render(request, "cars/manager.html", context)


@roles_required(Profile.ROLE_MANAGER, Profile.ROLE_ADMIN)
def create_customer_booking(request):
    if request.method != "POST":
        return redirect("manager_dashboard")
    customer = get_object_or_404(
        request.user.__class__,
        pk=request.POST.get("customer"),
        is_staff=False,
        profile__role=Profile.ROLE_CLIENT,
    )
    car = get_object_or_404(Car, pk=request.POST.get("car"))
    try:
        with transaction.atomic():
            car = Car.objects.select_for_update().get(pk=car.pk)
            now = timezone.now()
            Booking.objects.filter(
                car=car,
                status__in=(Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED),
                expires_at__lte=now,
            ).update(status=Booking.STATUS_EXPIRED)
            active = Booking.objects.filter(
                car=car,
                status__in=(Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED),
                expires_at__gt=now,
            ).exists()
            if active:
                raise ValueError("Для автомобиля уже существует активная бронь.")
            if car.status == Car.STATUS_BOOKED:
                car.status = Car.STATUS_AVAILABLE
                car.save(update_fields=["status"])
            if car.status != Car.STATUS_AVAILABLE:
                raise ValueError("Автомобиль недоступен для бронирования.")
            booking = Booking.objects.create(
                user=customer,
                car=car,
                status=Booking.STATUS_CREATED,
                deposit_kzt=500_000,
                expires_at=now + timedelta(days=3),
                comment=request.POST.get("comment", ""),
            )
            car.status = Car.STATUS_BOOKED
            car.save(update_fields=["status"])
        logger.info("Manager booking created: booking_id=%s car_id=%s customer_id=%s manager_id=%s", booking.pk, car.pk, customer.pk, request.user.pk)
        messages.success(request, f"Бронь для клиента создана (#{booking.pk}).")
    except ValueError as error:
        messages.error(request, str(error))
    return redirect("manager_dashboard")


@roles_required(Profile.ROLE_CASHIER, Profile.ROLE_ADMIN)
def cashier_dashboard(request):
    sales = Sale.objects.filter(status=Sale.STATUS_COMPLETED).select_related("customer", "car").order_by("-completed_at")[:50]
    return render(request, "cars/cashier.html", {"sales": sales, "payment_methods": Payment.METHOD_CHOICES})


@roles_required(Profile.ROLE_MANAGER, Profile.ROLE_ADMIN)
def create_sale(request):
    if request.method == "POST":
        car = get_object_or_404(Car, pk=request.POST.get("car"))
        customer = get_object_or_404(request.user.__class__, pk=request.POST.get("customer"))
        try:
            discount = int(request.POST.get("discount_kzt", "0"))
            payment_method = request.POST.get("payment_method", Sale.METHOD_TRANSFER)
            if discount < 0 or payment_method not in dict(Sale.PAYMENT_METHOD_CHOICES):
                raise ValueError("Проверьте размер скидки и способ оплаты.")
            with transaction.atomic():
                car = Car.objects.select_for_update().get(pk=car.pk)
                if car.status not in (Car.STATUS_AVAILABLE, Car.STATUS_BOOKED):
                    raise ValueError("Автомобиль недоступен для продажи.")
                sale = Sale.objects.create(
                    customer=customer, car=car, manager=request.user,
                    car_price_kzt=car.price_kzt, discount_kzt=discount,
                    payment_method=payment_method,
                    notes=request.POST.get("notes", ""),
                )
                for service_id in request.POST.getlist("services"):
                    service = get_object_or_404(Service, pk=service_id, is_active=True)
                    SaleService.objects.create(sale=sale, service=service, price_kzt=service.price_kzt)
                if request.POST.get("complete") == "on":
                    sale.status = Sale.STATUS_COMPLETED
                    sale.save()
                else:
                    car.status = Car.STATUS_PREPARING
                    car.save(update_fields=["status"])
                logger.info("Sale created: sale_id=%s car_id=%s customer_id=%s status=%s", sale.pk, car.pk, customer.pk, sale.status)
                messages.success(request, f"Сделка #{sale.pk} создана.")
                return redirect("manager_dashboard")
        except (ValueError, IntegrityError, ValidationError) as error:
            messages.error(request, str(error) or "Не удалось создать сделку.")
    context = {
        "cars": Car.objects.filter(status__in=[Car.STATUS_AVAILABLE, Car.STATUS_BOOKED]).order_by("brand", "model"),
        "customers": request.user.__class__.objects.filter(is_staff=False).order_by("username"),
        "services": Service.objects.filter(is_active=True),
        "payment_methods": Sale.PAYMENT_METHOD_CHOICES,
    }
    return render(request, "cars/sale_form.html", context)


@roles_required(Profile.ROLE_MANAGER, Profile.ROLE_ADMIN)
def update_sale_status(request, sale_id):
    if request.method != "POST":
        return redirect("manager_dashboard")
    try:
        with transaction.atomic():
            sale = get_object_or_404(Sale.objects.select_for_update(), pk=sale_id)
            car = Car.objects.select_for_update().get(pk=sale.car_id)
            if sale.status != Sale.STATUS_DRAFT:
                raise ValueError("Изменить можно только сделку в оформлении.")
            if request.POST.get("status") == Sale.STATUS_COMPLETED:
                sale.status = Sale.STATUS_COMPLETED
                sale.save()
                logger.info("Sale completed: sale_id=%s manager_id=%s", sale.pk, request.user.pk)
                messages.success(request, f"Продажа #{sale.pk} завершена.")
            elif request.POST.get("status") == Sale.STATUS_CANCELLED:
                sale.status = Sale.STATUS_CANCELLED
                sale.save()
                active_booking = Booking.objects.filter(
                    car=car,
                    status__in=(Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED),
                    expires_at__gt=timezone.now(),
                ).exists()
                car.status = Car.STATUS_BOOKED if active_booking else Car.STATUS_AVAILABLE
                car.save(update_fields=["status"])
                messages.success(request, f"Сделка #{sale.pk} отменена.")
            else:
                raise ValueError("Неизвестный статус сделки.")
    except (ValueError, ValidationError) as error:
        messages.error(request, str(error))
    return redirect("manager_dashboard")


@roles_required(Profile.ROLE_DIRECTOR, Profile.ROLE_ADMIN)
def reports_dashboard(request):
    start = request.GET.get("from")
    end = request.GET.get("to")
    for label, value in (("from", start), ("to", end)):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                messages.error(request, f"Некорректная дата в поле {label}.")
                return redirect("reports")
    sales = Sale.objects.filter(status=Sale.STATUS_COMPLETED)
    if start:
        sales = sales.filter(completed_at__date__gte=start)
    if end:
        sales = sales.filter(completed_at__date__lte=end)
    context = {
        "available_count": Car.objects.filter(status=Car.STATUS_AVAILABLE).count(),
        "sold_count": sales.count(),
        "revenue": sales.aggregate(value=Sum("total_kzt"))["value"] or 0,
        "average_sale": sales.aggregate(value=Avg("total_kzt"))["value"] or 0,
        "customers_count": Profile.objects.filter(role=Profile.ROLE_CLIENT).count(),
        "bookings_count": Booking.objects.count(),
        "drives_count": TestDrive.objects.count(),
        "popular_brands": sales.values("car__brand").annotate(count=Count("id")).order_by("-count")[:5],
        "popular_models": sales.values("car__brand", "car__model").annotate(count=Count("id")).order_by("-count")[:10],
        "manager_sales": sales.values("manager__username").annotate(count=Count("id"), revenue=Sum("total_kzt")).order_by("-revenue"),
        "service_sales": SaleService.objects.filter(sale__in=sales).values("service__name").annotate(count=Count("id"), revenue=Sum(F("price_kzt") * F("quantity"))).order_by("-revenue")[:10],
    }
    return render(request, "cars/reports.html", context)


@roles_required(Profile.ROLE_CASHIER, Profile.ROLE_ADMIN)
def register_sale_payment(request, sale_id):
    sale = get_object_or_404(Sale, pk=sale_id)
    if request.method == "POST":
        try:
            amount = int(request.POST.get("amount_kzt", "0"))
            method = request.POST.get("method", Payment.METHOD_TRANSFER)
            with transaction.atomic():
                sale = Sale.objects.select_for_update().get(pk=sale.pk)
                paid = sale.payments.filter(status=Payment.STATUS_PAID).aggregate(total=Sum("amount_kzt"))["total"] or 0
                if (
                    amount <= 0 or sale.status != Sale.STATUS_COMPLETED
                    or method not in dict(Payment.METHOD_CHOICES)
                    or paid + amount > sale.total_kzt
                ):
                    raise ValueError("Сумма платежа должна быть положительной и не превышать остаток по завершённой продаже.")
                Payment.objects.create(user=sale.customer, car=sale.car, sale=sale, amount_kzt=amount, status=Payment.STATUS_PAID, method=method)
            logger.info("Sale payment recorded: sale_id=%s cashier_id=%s amount_kzt=%s", sale.pk, request.user.pk, amount)
            messages.success(request, "Платёж зарегистрирован.")
        except ValueError as error:
            messages.error(request, str(error))
    profile = getattr(request.user, "profile", None)
    return redirect("cashier_dashboard" if profile and profile.role == Profile.ROLE_CASHIER else "manager_dashboard")
