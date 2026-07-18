# Frontend API Alignment Guide

This document outlines the API contract changes implemented on the backend. Ensure your Next.js frontend is aligned to match these updates.

## 📌 Summary of Contract Changes

| Feature | Change Type | Frontend Action Required |
|---------|-------------|--------------------------|
| **1. Student check-in tokens** | Secure Filter | **None** (Still visible for Terminal/Staff/Admin roles, hidden only from unauthorized roles like other students/teachers). |
| **2. Timetable creation/modification** | Writable Payload | Update POST/PUT payloads to send flat key IDs (e.g. `class_obj_id`, `subject_id`, `teacher_id`) instead of nested relation objects. |
| **3. API list endpoints** | Response Shape | Update fetch logic on lists to unwrap `.results` (due to standard `PageNumberPagination` being enabled with page size 50). |
| **4. User updates** | Writable Serializer | Writable username/email/role/is_active fields are now enabled for Admin requests. |

---

## 1. Role-based Permission Locking for `check_in_token`

### Affected Endpoints
- `GET /api/v1/students/` (List)
- `GET /api/v1/students/{id}/` (Detail)

### Status: Backwards Compatible (No Frontend Changes Required)
We chose **not** to remove `check_in_token` completely. Instead, the backend now checks authorization context dynamically in the serializer:
- **Visible to**: Users with roles `admin`, `staff`, `terminal`, and the specific student owner whose account is linked to the student record.
- **Hidden from**: Other students and teachers (the field will simply be excluded from the JSON response).

### How this affects the Frontend:
- **QR Terminal page**: Accesses the API as the `terminal` role. `check_in_token` remains present in the list, so matching logic (`students.find((s) => s.check_in_token === token)`) will continue to work perfectly.
- **Check-In Management page**: Accesses the API as `staff` or `admin`. `check_in_token` remains visible for display and rendering QR codes.
- **Other users**: Students viewing other student profiles, or teachers viewing class lists, will not see the tokens. No client changes are needed!

---

## 2. Timetable Slot & Student Writable Fields

### Affected Endpoints
- `POST /api/v1/timetable-slots/`
- `PUT /api/v1/timetable-slots/{id}/`
- `PATCH /api/v1/timetable-slots/{id}/`
- `POST /api/v1/timetable-students/`

### Current Request Body
DRF currently expects nested objects for relations because the serializer has no writable ID fields defined:
```json
{
  "class_obj": { "id": 1 },
  "subject": { "id": 2 },
  "teacher": { "id": 3 },
  "day_of_week": 0,
  "start_time": "09:00:00",
  "end_time": "10:00:00",
  "room": "Room 101"
}
```

### New Request Body (After Fix)
You can directly pass the primary key IDs as integer values using the `*_id` fields:
```json
{
  "class_obj_id": 1,
  "subject_id": 2,
  "teacher_id": 3,
  "day_of_week": 0,
  "start_time": "09:00:00",
  "end_time": "10:00:00",
  "room": "Room 101"
}
```

### How to Align the Frontend
Update the form submission handler to send flat properties instead of nested structures:

```typescript
// Old payload sent
const payload = {
  class_obj: { id: form.classId },
  subject: { id: form.subjectId },
  teacher: { id: form.teacherId },
  day_of_week: form.dayOfWeek,
  start_time: form.startTime,
  end_time: form.endTime,
  room: form.room
};

// New payload to send
const payload = {
  class_obj_id: form.classId,
  subject_id: form.subjectId,
  teacher_id: form.teacherId,
  day_of_week: form.dayOfWeek,
  start_time: form.startTime,
  end_time: form.endTime,
  room: form.room
};
```

---

## 3. DRF Pagination on All List Endpoints

### Affected Endpoints
All GET list endpoints (`/api/v1/students/`, `/api/v1/teachers/`, `/api/v1/sessions/`, etc.)

### Current Response Format
```json
[
  { "id": 1, "name": "Alice" },
  { "id": 2, "name": "Bob" }
]
```

### New Response Format (After Fix)
```json
{
  "count": 105,
  "next": "http://localhost:8000/api/v1/students/?page=2",
  "previous": null,
  "results": [
    { "id": 1, "name": "Alice" },
    { "id": 2, "name": "Bob" }
  ]
}
```

### How to Align the Frontend
Any API fetch that reads a list must unwrap the `.results` field from the response:

```typescript
// Old way
const response = await fetch('/api/v1/students/');
const students = await response.json(); // array of students

// New way
const response = await fetch('/api/v1/students/');
const data = await response.json();
const students = data.results; // array of students
const totalCount = data.count; // total records in database
```

---

## 4. User Serialization & Update Endpoint

### Affected Endpoints
- `PUT /api/v1/users/{id}/`
- `PATCH /api/v1/users/{id}/`

### Current Request Body
Currently, all fields are read-only in `UserSerializer`. Sending update requests returns a 200 OK but silently ignores updates.

### New Request Body (After Fix)
Admin users can edit the following fields:
```json
{
  "username": "new_username",
  "email": "user@example.com",
  "role": "teacher",
  "is_active": true
}
```
*(Response will echo back the updated object structure).*
