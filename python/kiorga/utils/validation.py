import logging
from typing import Callable, List, Optional, Type, TypeVar

from kiorga.datamodel import task_pb2
from google.protobuf import json_format
from google.protobuf.message import Message

# Generic TypeVar für Protobuf-Nachrichten, um Typsicherheit zu gewährleisten
T = TypeVar('T', bound=Message)

def parse_and_validate_message(
    json_string: str,
    message_class: Type[T],
    validator_func: Optional[Callable[[T], List[str]]] = None
) -> T:
    """
    Parst einen JSON-String in eine Protobuf-Nachricht, validiert sie optional und gibt sie zurück.
    """
    try:
        message_instance = message_class()
        json_format.Parse(json_string, message_instance)
    except json_format.ParseError as e:
        logging.error(f"Protobuf-Deserialisierung für {message_class.__name__} fehlgeschlagen: {e}", exc_info=True)
        raise ValueError(f"protobuf parse error for {message_class.__name__}") from e

    if validator_func and (errors := validator_func(message_instance)):
        error_msg = f"Validierung für {message_class.__name__} fehlgeschlagen. Fehlerhafte Felder: {errors}"
        raise ValueError(error_msg)

    return message_instance

def validate_task(task: task_pb2.Task) -> list[str]:
    """
    Prüft, ob die Pflichtfelder im Task-Objekt für eine gültige Verarbeitung gesetzt sind.
    
    Gibt eine Liste von Fehlermeldungen zurück. Eine leere Liste bedeutet,
    dass der Task gültig ist.
    """
    errors = []
    if not task.task_id:
        errors.append("task_id fehlt")
    if not task.title or len(task.title.strip()) == 0:
        errors.append("title fehlt oder ist leer")
    if not task.description or len(task.description.strip()) == 0:
        errors.append("description fehlt oder ist leer")

    # Prüft, ob Status und Priorität gültige Enum-Werte sind.
    # `TASK_STATUS_UNSPECIFIED` und `TASK_PRIORITY_UNSPECIFIED` sind gültig,
    # da sie die Standardwerte sind, wenn nichts explizit gesetzt wird.
    valid_status_values = [
        task_pb2.TaskStatus.TASK_STATUS_UNSPECIFIED,
        task_pb2.TaskStatus.TASK_STATUS_PENDING,
        task_pb2.TaskStatus.TASK_STATUS_COMPLETED,
        task_pb2.TaskStatus.TASK_STATUS_IN_PROGRESS,
        task_pb2.TaskStatus.TASK_STATUS_FAILED,
    ]
    if task.status not in valid_status_values:
        errors.append(f"status ist ungültig: {task.status}")

    valid_priority_values = [
        task_pb2.TaskPriority.TASK_PRIORITY_UNSPECIFIED,
        task_pb2.TaskPriority.TASK_PRIORITY_LOW,
        task_pb2.TaskPriority.TASK_PRIORITY_MEDIUM,
        task_pb2.TaskPriority.TASK_PRIORITY_HIGH,
        task_pb2.TaskPriority.TASK_PRIORITY_URGENT,
        task_pb2.TaskPriority.TASK_PRIORITY_OPTIONAL,
    ]
    if task.priority not in valid_priority_values:
        errors.append(f"priority ist ungültig: {task.priority}")

    if not task.creator_agent_id:
        errors.append("creator_agent_id fehlt")
    # Ein gültiger Zeitstempel muss gesetzt sein.
    if not task.created_at or getattr(task.created_at, "seconds", 0) == 0:
        errors.append("created_at fehlt oder ist ungültig")
    return errors