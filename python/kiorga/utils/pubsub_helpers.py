import base64
import logging
import time
from datetime import datetime

from google.api_core import exceptions
from google.cloud import pubsub_v1
from google.protobuf import json_format
from google.protobuf.message import Message

def decode_pubsub_message(envelope: dict) -> tuple[str, float]:
    """
    Dekodiert eine Pub/Sub-Nachrichtenhülle (Envelope).

    Extrahiert und dekodiert die Base64-kodierten Daten aus einer Pub/Sub-Nachricht
    und gibt den resultierenden JSON-String sowie den Veröffentlichungszeitstempel zurück.

    Args:
        envelope: Die Pub/Sub-Nachrichtenhülle als Dictionary.

    Returns:
        Ein Tupel, das den dekodierten JSON-String und den Veröffentlichungszeitstempel
        als Float enthält.

    Raises:
        ValueError: Wenn das Nachrichtenformat ungültig ist oder die Dekodierung fehlschlägt.
    """
    if not isinstance(envelope, dict) or "message" not in envelope:
        raise ValueError("invalid Pub/Sub message format")

    pubsub_message = envelope["message"]
    if not isinstance(pubsub_message, dict) or "data" not in pubsub_message:
        raise ValueError("Pub/Sub message missing 'data' field")

    publish_time_str = pubsub_message.get("publish_time")
    publish_timestamp = time.time()  # Fallback auf aktuelle Zeit
    if publish_time_str:
        try:
            # Korrekter Umgang mit 'Z' für die UTC-Zeitzone
            dt_object = datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
            publish_timestamp = dt_object.timestamp()
        except ValueError:
            logging.warning(f"Konnte publish_time '{publish_time_str}' nicht parsen. Verwende Fallback.")

    try:
        data_bytes = base64.b64decode(pubsub_message["data"])
        json_string_received = data_bytes.decode('utf-8')
        return json_string_received, publish_timestamp
    except Exception as e:
        logging.error(f"Base64-Dekodierung fehlgeschlagen: {e}", exc_info=True)
        raise ValueError("base64 decode error") from e


def publish_proto_message_as_json(
    publisher: pubsub_v1.PublisherClient,
    project_id: str,
    topic_id: str,
    proto_message: Message,
) -> str:
    """
    Serialisiert eine Protobuf-Nachricht nach JSON, kodiert sie und veröffentlicht sie in Pub/Sub.

    Args:
        publisher: Eine Instanz des pubsub_v1.PublisherClient.
        project_id: Die Google Cloud Projekt-ID.
        topic_id: Die ID des Pub/Sub-Topics.
        proto_message: Die zu sendende Protobuf-Nachricht.

    Returns:
        Die Message-ID der veröffentlichten Nachricht.

    Raises:
        IOError: Wenn das Veröffentlichen in Pub/Sub fehlschlägt.
        ValueError: Wenn die Serialisierung der Nachricht fehlschlägt.
    """
    try:
        # 1. Protobuf-Nachricht in einen JSON-String konvertieren.
        json_string = json_format.MessageToJson(proto_message)
        data_to_send = json_string.encode("utf-8")

        # 2. Nachricht veröffentlichen.
        topic_path = publisher.topic_path(project_id, topic_id)
        future = publisher.publish(topic_path, data=data_to_send)
        message_id = future.result(timeout=30)
        logging.info(f"Nachricht erfolgreich an Topic '{topic_id}' veröffentlicht. Message ID: {message_id}")
        return message_id
    except exceptions.GoogleAPICallError as e:
        logging.error(f"Fehler bei der Pub/Sub-API während des Veröffentlichens an Topic '{topic_id}': {e}")
        raise IOError(f"Pub/Sub API error on topic {topic_id}") from e
    except Exception as e:
        logging.error(f"Ein unerwarteter Fehler ist beim Veröffentlichen an Topic '{topic_id}' aufgetreten: {e}")
        raise IOError(f"Unexpected error publishing to topic {topic_id}") from e