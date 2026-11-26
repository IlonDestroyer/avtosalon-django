from rest_framework.routers import DefaultRouter

from .api_views import BookingViewSet, CarViewSet, FavoriteViewSet, StaffSalesViewSet, TestDriveViewSet

router = DefaultRouter()
router.register("cars", CarViewSet, basename="api-cars")
router.register("bookings", BookingViewSet, basename="api-bookings")
router.register("test-drives", TestDriveViewSet, basename="api-test-drives")
router.register("favorites", FavoriteViewSet, basename="api-favorites")
router.register("sales", StaffSalesViewSet, basename="api-sales")

urlpatterns = router.urls
