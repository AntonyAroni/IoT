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
        r.reset_window()
        r.last_rssi = None
        repo.save_record(r)
    return {"status": "success", "message": f"Asistencia del aula {room_id} reiniciada."}
