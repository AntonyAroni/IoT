"""
Controlador HTTP: Consulta y Gestión de Asistencia Escolar.
Permite que el Dashboard de Aula en la laptop consulte el padrón y estados en tiempo real.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from ..repositories.base import IAttendanceRepository
from ..domain.attendance import AttendanceStatus

router = APIRouter(prefix="/api/v1/attendance", tags=["Attendance"])

def get_attendance_repo() -> IAttendanceRepository:
    from ..main import app_state
    return app_state.attendance_repo

@router.get("/room/{room_id}")
def get_room_attendance(room_id: str, repo: IAttendanceRepository = Depends(get_attendance_repo)) -> Dict[str, Any]:
    """Retorna la lista de asistencia y métricas del aula solicitada."""
    records = repo.get_room_records(room_id)
    students = repo.get_students_for_room(room_id)

    total_enrolled = len(students)
    confirmed_count = sum(1 for r in records if r.status == AttendanceStatus.PRESENT_CONFIRMED)
    approaching_count = sum(1 for r in records if r.status in (AttendanceStatus.APPROACHING, AttendanceStatus.AT_DOOR))

    return {
        "room_id": room_id,
        "total_enrolled": total_enrolled,
        "present_confirmed": confirmed_count,
        "approaching": approaching_count,
        "attendance_rate_percent": round((confirmed_count / total_enrolled * 100) if total_enrolled > 0 else 0, 1),
        "records": [r.to_dict() for r in records]
    }

@router.post("/room/{room_id}/reset")
def reset_room_attendance(room_id: str, repo: IAttendanceRepository = Depends(get_attendance_repo)) -> Dict[str, str]:
    """Reinicia la asistencia del aula para iniciar una nueva clase o demo."""
    records = repo.get_room_records(room_id)
    for r in records:
        r.status = AttendanceStatus.ABSENT
        r.confirmed_at = None
        r.samples_in_window = 0
        r.last_rssi = None
        repo.save_record(r)
    return {"status": "success", "message": f"Asistencia del aula {room_id} reiniciada."}

@router.get("/students")
def get_all_students(repo: IAttendanceRepository = Depends(get_attendance_repo)) -> List[Dict[str, Any]]:
    """Retorna la lista de todos los estudiantes registrados en el sistema."""
    students = repo.get_all_students()
    return [{"id": s.id, "name": s.name, "enrolled_room": s.enrolled_room} for s in students]

from pydantic import BaseModel, Field
class StudentRegisterRequest(BaseModel):
    id: str = Field(..., description="Identificador único del estudiante (ej. EST_15)")
    name: str = Field(..., description="Nombre completo del estudiante")
    enrolled_room: str = Field(..., description="Aula asignada (ej. S302)")

@router.post("/students")
def register_student_endpoint(payload: StudentRegisterRequest, repo: IAttendanceRepository = Depends(get_attendance_repo)) -> Dict[str, Any]:
    """Registra dinámicamente un nuevo estudiante en el sistema."""
    from ..domain.attendance import Student
    student = Student(id=payload.id, name=payload.name, enrolled_room=payload.enrolled_room)
    repo.register_student(student)
    return {
        "status": "success",
        "message": f"Estudiante '{student.name}' registrado exitosamente.",
        "student": {"id": student.id, "name": student.name, "enrolled_room": student.enrolled_room}
    }
