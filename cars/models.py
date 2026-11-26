from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db import models
from django.db import transaction
from django.core.validators import MinValueValidator, RegexValidator
from django.utils import timezone
from django.utils.text import slugify
import uuid


class Profile(models.Model):
    ROLE_CLIENT = "client"
    ROLE_MANAGER = "manager"
    ROLE_CASHIER = "cashier"
    ROLE_ADMIN = "admin"
    ROLE_DIRECTOR = "director"
    ROLE_CHOICES = [
        (ROLE_CLIENT, "Клиент"),
        (ROLE_MANAGER, "Менеджер"),
        (ROLE_CASHIER, "Кассир"),
        (ROLE_ADMIN, "Администратор"),
        (ROLE_DIRECTOR, "Руководитель"),
    ]
    ADMIN_GROUP_NAME = "Автосалон — администраторы"
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    full_name = models.CharField("ФИО", max_length=200, blank=True)
    phone = models.CharField("Телефон", max_length=30, blank=True)
    address = models.CharField("Адрес", max_length=300, blank=True)
    iin = models.CharField("ИИН", max_length=12, blank=True)
    role = models.CharField("Роль", max_length=20, choices=ROLE_CHOICES, default=ROLE_CLIENT)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.iin and (len(self.iin) != 12 or not self.iin.isdigit()):
            raise ValidationError({"iin": "ИИН должен содержать ровно 12 цифр."})

    def save(self, *args, **kwargs):
        previous_role = None
        if self.pk:
            previous_role = Profile.objects.filter(pk=self.pk).values_list("role", flat=True).first()
        super().save(*args, **kwargs)
        if self.role == self.ROLE_ADMIN:
            group, _ = Group.objects.get_or_create(name=self.ADMIN_GROUP_NAME)
            group.permissions.set(Permission.objects.all())
            self.user.groups.add(group)
            if not self.user.is_staff:
                self.user.is_staff = True
                self.user.save(update_fields=["is_staff"])
        elif previous_role == self.ROLE_ADMIN:
            self.user.groups.remove(*Group.objects.filter(name=self.ADMIN_GROUP_NAME))
            if not self.user.is_superuser:
                self.user.is_staff = False
                self.user.save(update_fields=["is_staff"])

    class Meta:
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"

    def __str__(self):
        return self.full_name or self.user.username


class Car(models.Model):
    STATUS_AVAILABLE = "available"
    STATUS_BOOKED = "booked"
    STATUS_SOLD = "sold"
    STATUS_IN_TRANSIT = "in_transit"
    STATUS_PREPARING = "preparing"
    STATUS_SERVICE = "service"
    STATUS_UNLISTED = "unlisted"
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "В наличии"),
        (STATUS_BOOKED, "Забронирован"),
        (STATUS_PREPARING, "Оформляется"),
        (STATUS_SOLD, "Продан"),
        (STATUS_IN_TRANSIT, "В пути"),
        (STATUS_SERVICE, "На обслуживании"),
        (STATUS_UNLISTED, "Снят с продажи"),
    ]
    TYPE_NEW = "new"
    TYPE_USED = "used"
    TYPE_CHOICES = [(TYPE_NEW, "Новый"), (TYPE_USED, "С пробегом")]
    BODY_CHOICES = [
        ("Седан", "Седан"), ("Хэтчбек", "Хэтчбек"), ("Универсал", "Универсал"),
        ("Кроссовер", "Кроссовер"), ("Внедорожник", "Внедорожник"),
        ("Минивэн", "Минивэн"), ("Купе", "Купе"), ("Пикап", "Пикап"),
        ("Электромобиль", "Электромобиль"),
    ]

    slug = models.SlugField(max_length=200, unique=True, blank=True)
    brand = models.CharField("Марка", max_length=100)
    model = models.CharField("Модель", max_length=100)
    brand_catalog = models.ForeignKey("Brand", on_delete=models.SET_NULL, null=True, blank=True, related_name="cars")
    model_catalog = models.ForeignKey("CarModel", on_delete=models.SET_NULL, null=True, blank=True, related_name="cars")
    stock_number = models.CharField("Внутренний номер", max_length=40, unique=True, null=True, blank=True)
    vin = models.CharField(
        "VIN", max_length=17, unique=True, null=True, blank=True,
        validators=[RegexValidator(r"^[A-HJ-NPR-Z0-9]{17}$", "VIN должен состоять из 17 символов (без I, O и Q).")],
    )
    trim = models.CharField("Комплектация", max_length=100, blank=True)
    year = models.PositiveIntegerField("Год выпуска")
    body = models.CharField("Кузов", max_length=50, choices=BODY_CHOICES, default="Седан")
    engine_type = models.CharField("Тип двигателя", max_length=50, blank=True)
    engine_volume = models.DecimalField("Объём двигателя, л", max_digits=4, decimal_places=1, null=True, blank=True)
    mileage_km = models.PositiveIntegerField("Пробег, км", default=0)
    fuel = models.CharField("Топливо", max_length=50, default="Бензин")
    horsepower = models.PositiveIntegerField("Мощность, л.с.", default=150)
    transmission = models.CharField("Коробка", max_length=50, default="Автомат")
    drivetrain = models.CharField("Привод", max_length=30, blank=True)
    color = models.CharField("Цвет", max_length=50, blank=True)
    car_type = models.CharField("Состояние", max_length=10, choices=TYPE_CHOICES, default=TYPE_USED)
    price_kzt = models.PositiveIntegerField("Цена, ₸", validators=[MinValueValidator(1)])
    purchase_price_kzt = models.PositiveIntegerField("Закупочная стоимость, ₸", default=0)
    arrival_date = models.DateField("Дата поступления", null=True, blank=True)
    storage_location = models.CharField("Место хранения", max_length=100, blank=True)
    supplier = models.ForeignKey("Supplier", on_delete=models.SET_NULL, null=True, blank=True, related_name="cars")
    sold_at = models.DateTimeField("Дата продажи", null=True, blank=True)
    image = models.ImageField("Фото", upload_to="cars/", blank=True, null=True)
    image_url = models.URLField("Ссылка на фото", blank=True)
    description = models.TextField("Описание", blank=True)
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_AVAILABLE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Автомобиль"
        verbose_name_plural = "Автомобили"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def title(self):
        parts = [self.brand, self.model, self.trim]
        return " ".join(p for p in parts if p)

    def get_image_url(self):
        if self.image:
            return self.image.url
        if self.image_url:
            return self.image_url
        return ""

    def save(self, *args, **kwargs):
        if self.brand and not self.brand_catalog_id:
            self.brand_catalog, _ = Brand.objects.get_or_create(name=self.brand)
        if self.model and self.brand_catalog_id and not self.model_catalog_id:
            self.model_catalog, _ = CarModel.objects.get_or_create(brand=self.brand_catalog, name=self.model)
        if not self.slug:
            base = slugify(f"{self.brand}-{self.model}-{self.trim}", allow_unicode=True)
            if not base:
                base = "car"
            self.slug = f"{base}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)


class Booking(models.Model):
    STATUS_CREATED = "created"
    STATUS_CONFIRMED = "confirmed"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Создана"),
        (STATUS_CONFIRMED, "Подтверждена"),
        (STATUS_COMPLETED, "Завершена"),
        (STATUS_CANCELLED, "Отменена"),
        (STATUS_EXPIRED, "Просрочена"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="bookings")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_CREATED,
    )
    deposit_kzt = models.PositiveIntegerField("Предоплата, ₸", default=500_000)
    expires_at = models.DateTimeField("Действует до")
    comment = models.TextField("Комментарий", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Бронь"
        verbose_name_plural = "Брони"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Бронь {self.car} — {self.user}"

    def is_active(self):
        return self.status in (self.STATUS_CREATED, self.STATUS_CONFIRMED) and self.expires_at > timezone.now()


class TestDrive(models.Model):
    STATUS_PLANNED = "planned"
    STATUS_CONFIRMED = "confirmed"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"
    STATUS_NO_SHOW = "no_show"
    STATUS_CHOICES = [
        (STATUS_PLANNED, "Запланирован"),
        (STATUS_CONFIRMED, "Подтверждён"),
        (STATUS_DONE, "Проведён"),
        (STATUS_CANCELLED, "Отменён"),
        (STATUS_NO_SHOW, "Клиент не явился"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="test_drives",
    )
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="test_drives")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PLANNED,
    )
    scheduled_at = models.DateTimeField("Дата и время")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Тест-драйв"
        verbose_name_plural = "Тест-драйвы"
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"Тест-драйв {self.car} — {self.scheduled_at:%d.%m.%Y %H:%M}"


class Payment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "В обработке"),
        (STATUS_PAID, "Оплачен"),
        (STATUS_FAILED, "Не прошёл"),
    ]
    METHOD_CARD = "card"
    METHOD_TRANSFER = "transfer"
    METHOD_CHOICES = [
        (METHOD_CARD, "Карта"),
        (METHOD_TRANSFER, "Перевод"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="payments")
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    sale = models.ForeignKey("Sale", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    order_no = models.CharField("Номер заказа", max_length=50, unique=True)
    amount_kzt = models.PositiveIntegerField("Сумма, ₸", validators=[MinValueValidator(1)])
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    method = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        default=METHOD_CARD,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_no} — {self.amount_kzt} ₸"

    def save(self, *args, **kwargs):
        if not self.order_no:
            self.order_no = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class Brand(models.Model):
    name = models.CharField("Марка", max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Марка"
        verbose_name_plural = "Марки"

    def __str__(self):
        return self.name


class CarModel(models.Model):
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name="models", verbose_name="Марка")
    name = models.CharField("Модель", max_length=100)

    class Meta:
        ordering = ["brand__name", "name"]
        constraints = [models.UniqueConstraint(fields=["brand", "name"], name="unique_brand_model")]
        verbose_name = "Модель автомобиля"
        verbose_name_plural = "Модели автомобилей"

    def __str__(self):
        return f"{self.brand} {self.name}"


class CarImage(models.Model):
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField("Изображение", upload_to="cars/gallery/")
    caption = models.CharField("Подпись", max_length=150, blank=True)
    position = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = "Фото автомобиля"
        verbose_name_plural = "Фотографии автомобилей"


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "car"], name="unique_user_favorite")]
        ordering = ["-created_at"]
        verbose_name = "Избранное"
        verbose_name_plural = "Избранное"


class Supplier(models.Model):
    name = models.CharField("Название", max_length=200)
    bin = models.CharField("БИН", max_length=12, blank=True)
    contact_name = models.CharField("Контактное лицо", max_length=150, blank=True)
    phone = models.CharField("Телефон", max_length=30, blank=True)
    email = models.EmailField("Email", blank=True)
    address = models.CharField("Адрес", max_length=300, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Поставщик"
        verbose_name_plural = "Поставщики"

    def __str__(self):
        return self.name


class Delivery(models.Model):
    STATUS_EXPECTED = "expected"
    STATUS_RECEIVED = "received"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_EXPECTED, "Ожидается"),
        (STATUS_RECEIVED, "Получена"),
        (STATUS_CANCELLED, "Отменена"),
    ]
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="deliveries")
    car = models.ForeignKey(Car, on_delete=models.PROTECT, related_name="deliveries")
    expected_at = models.DateField("Ожидаемая дата", null=True, blank=True)
    received_at = models.DateField("Дата поступления", null=True, blank=True)
    purchase_price_kzt = models.PositiveIntegerField("Закупочная стоимость, ₸", default=0)
    status = models.CharField("Статус", max_length=15, choices=STATUS_CHOICES, default=STATUS_EXPECTED)
    notes = models.TextField("Комментарий", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Поставка"
        verbose_name_plural = "Поставки"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.status == self.STATUS_EXPECTED and self.car.status not in (Car.STATUS_SOLD, Car.STATUS_SERVICE):
                self.car.supplier = self.supplier
                self.car.status = Car.STATUS_IN_TRANSIT
                self.car.save(update_fields=["supplier", "status"])
            if self.status == self.STATUS_RECEIVED:
                self.car.supplier = self.supplier
                self.car.purchase_price_kzt = self.purchase_price_kzt
                self.car.arrival_date = self.received_at or timezone.localdate()
                self.car.status = Car.STATUS_AVAILABLE
                self.car.save(update_fields=["supplier", "purchase_price_kzt", "arrival_date", "status"])
            super().save(*args, **kwargs)


class Service(models.Model):
    name = models.CharField("Услуга", max_length=150, unique=True)
    description = models.TextField("Описание", blank=True)
    price_kzt = models.PositiveIntegerField("Цена, ₸", validators=[MinValueValidator(0)])
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Дополнительная услуга"
        verbose_name_plural = "Дополнительные услуги"

    def __str__(self):
        return self.name


class Sale(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Оформляется"),
        (STATUS_COMPLETED, "Завершена"),
        (STATUS_CANCELLED, "Отменена"),
    ]
    METHOD_CASH = "cash"
    METHOD_CARD = "card"
    METHOD_TRANSFER = "transfer"
    METHOD_CREDIT = "credit"
    PAYMENT_METHOD_CHOICES = [
        (METHOD_CASH, "Наличные"),
        (METHOD_CARD, "Карта"),
        (METHOD_TRANSFER, "Перевод"),
        (METHOD_CREDIT, "Кредит"),
    ]
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")
    car = models.ForeignKey(Car, on_delete=models.PROTECT, related_name="sales")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="managed_sales")
    car_price_kzt = models.PositiveIntegerField("Стоимость автомобиля, ₸")
    discount_kzt = models.PositiveIntegerField("Скидка, ₸", default=0)
    total_kzt = models.PositiveBigIntegerField("Итого, ₸", default=0)
    payment_method = models.CharField("Способ оплаты", max_length=15, choices=PAYMENT_METHOD_CHOICES, default=METHOD_TRANSFER)
    status = models.CharField("Статус сделки", max_length=15, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    completed_at = models.DateTimeField("Дата продажи", null=True, blank=True)
    notes = models.TextField("Комментарий", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Продажа"
        verbose_name_plural = "Продажи"

    def __str__(self):
        return f"Продажа #{self.pk}: {self.car}"

    def calculate_total(self):
        services_total = sum(item.price_kzt * item.quantity for item in self.sale_services.all())
        return self.car_price_kzt + services_total - self.discount_kzt

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if self.status == self.STATUS_COMPLETED:
            if self.car.status == Car.STATUS_SOLD and not (self.pk and Sale.objects.filter(pk=self.pk, status=self.STATUS_COMPLETED).exists()):
                raise ValidationError({"car": "Этот автомобиль уже продан."})
            if Sale.objects.filter(car=self.car, status=self.STATUS_COMPLETED).exclude(pk=self.pk).exists():
                raise ValidationError({"car": "Для автомобиля уже существует завершённая продажа."})
            self.completed_at = self.completed_at or timezone.now()
        services_total = 0
        if self.pk:
            services_total = sum(item.price_kzt * item.quantity for item in self.sale_services.all())
        self.total_kzt = self.car_price_kzt + services_total - self.discount_kzt
        if self.total_kzt < 0:
            raise ValidationError({"discount_kzt": "Скидка не может превышать сумму сделки."})
        super().save(*args, **kwargs)
        if self.status == self.STATUS_COMPLETED:
            Car.objects.filter(pk=self.car_id).update(status=Car.STATUS_SOLD, sold_at=self.completed_at)
            Booking.objects.filter(
                car_id=self.car_id,
                status__in=[Booking.STATUS_CREATED, Booking.STATUS_CONFIRMED],
            ).update(status=Booking.STATUS_COMPLETED)


class SaleService(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="sale_services")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="sale_services")
    price_kzt = models.PositiveIntegerField("Цена на момент продажи", validators=[MinValueValidator(0)])
    quantity = models.PositiveSmallIntegerField("Количество", default=1, validators=[MinValueValidator(1)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["sale", "service"], name="unique_service_per_sale")]
        verbose_name = "Услуга в продаже"
        verbose_name_plural = "Услуги в продаже"

    def save(self, *args, **kwargs):
        if not self.price_kzt:
            self.price_kzt = self.service.price_kzt
        super().save(*args, **kwargs)
        if self.sale_id:
            self.sale.save(update_fields=["total_kzt"])

    def delete(self, *args, **kwargs):
        sale = self.sale
        result = super().delete(*args, **kwargs)
        sale.save(update_fields=["total_kzt"])
        return result
