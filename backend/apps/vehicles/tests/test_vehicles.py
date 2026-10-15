from apps.accounts.models import Role
from apps.core.tests.factories import BaseAPITest, make_customer, make_policy, make_staff, make_vehicle

VEHICLE = {"registration_number": "mh 02 ab 1234", "make": "Maruti Suzuki", "model": "Swift", "vehicle_type": "CAR",
           "manufacturing_year": 2021, "registration_date": "2021-04-01", "purchase_date": "2021-03-25",
           "engine_number": "k12mn123456", "chassis_number": "MA3FJEB1S00123456", "color": "White",
           "owner_name": "Test Owner"}


class VehicleTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.owner = make_customer()
        self.c = self.client_for(self.owner)

    def test_register_vehicle_normalises_registration(self):
        r = self.c.post("/api/vehicles/", VEHICLE, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["registration_number"], "MH02AB1234")
        self.assertFalse(r.data["is_locked"])

    def test_duplicate_registration_rejected(self):
        self.c.post("/api/vehicles/", VEHICLE, format="json")
        other = self.client_for(make_customer())
        dup = {**VEHICLE, "registration_number": "MH02AB1234", "engine_number": "X1", "chassis_number": "Y1"}
        r = other.post("/api/vehicles/", dup, format="json")
        self.assertEqual(r.status_code, 409)                        # REQ-VEH-004
        self.assertEqual(r.data["error"]["code"], "duplicate_registration_number")

    def test_future_dates_and_years_rejected(self):
        r = self.c.post("/api/vehicles/", {**VEHICLE, "manufacturing_year": 2099}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_customers_cannot_see_other_customers_vehicles(self):
        theirs = make_vehicle(make_customer())
        self.assertEqual(self.c.get(f"/api/vehicles/{theirs.pk}/").status_code, 404)      # IDOR → 404
        self.assertEqual(self.c.patch(f"/api/vehicles/{theirs.pk}/", {"color": "Red"}, format="json").status_code, 404)
        self.assertEqual(self.c.get("/api/vehicles/").data["count"], 0)

    def test_vehicle_locked_after_policy_association(self):
        v = make_vehicle(self.owner)
        self.assertEqual(self.c.patch(f"/api/vehicles/{v.pk}/", {"color": "Blue"}, format="json").status_code, 200)
        make_policy(v)
        r = self.c.patch(f"/api/vehicles/{v.pk}/", {"color": "Red"}, format="json")
        self.assertEqual(r.status_code, 409)                        # REQ-VEH-009
        self.assertEqual(r.data["error"]["code"], "vehicle_locked")

    def test_vehicles_cannot_be_deleted(self):
        v = make_vehicle(self.owner)
        self.assertEqual(self.c.delete(f"/api/vehicles/{v.pk}/").status_code, 405)   # REQ-VEH-010

    def test_staff_read_only(self):
        adjuster = self.client_for(make_staff(Role.ADJUSTER))
        v = make_vehicle(self.owner)
        self.assertEqual(adjuster.get(f"/api/vehicles/{v.pk}/").status_code, 200)
        self.assertEqual(adjuster.post("/api/vehicles/", VEHICLE, format="json").status_code, 403)
