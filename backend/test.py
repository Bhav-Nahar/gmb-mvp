from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import get_current_user, staff_required
from app.models.user import User

def override_user():
    return User(id=1, organization_id=1, role='Admin')

app.dependency_overrides[get_current_user] = override_user
app.dependency_overrides[staff_required] = override_user

client = TestClient(app)
resp = client.get('/api/v1/locations/1/form-schema')
print("Status:", resp.status_code)
print("Response:", resp.text)
