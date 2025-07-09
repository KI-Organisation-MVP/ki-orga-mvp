import logging
from fastapi import FastAPI, Request, HTTPException

def create_app(service_handler: object, process_method_name: str) -> FastAPI:
    """
    Erstellt und konfiguriert eine FastAPI-Anwendung mit einem generischen Pub/Sub-Endpunkt.

    Diese Factory zentralisiert die Erstellung der App, das Routing und die Fehlerbehandlung
    für alle Pub/Sub-basierten Services.

    Args:
        service_handler: Eine Instanz der Service-Klasse (z.B. TaskHandler, TaskHandler).
        process_method_name: Der Name der Methode auf dem Service-Handler, die die
                             eigentliche Verarbeitungslogik enthält (z.B. "handle_task").

    Returns:
        Eine konfigurierte FastAPI-Anwendungsinstanz.
    """
    app = FastAPI()

    @app.post("/")
    async def index(request: Request):
        """
        Empfängt eine Pub/Sub-Nachricht und übergibt sie zur Verarbeitung an den Service-Layer.
        """
        envelope = await request.json()
        if not envelope:
            msg = "no Pub/Sub message received"
            logging.error(msg)
            raise HTTPException(status_code=400, detail=f"Bad Request: {msg}")

        try:
            handler_method = getattr(service_handler, process_method_name)
            handler_method(envelope)
            return "", 204
        except ValueError as e:
            logging.warning(f"Bad Request bei der Verarbeitung: {e}")
            raise HTTPException(status_code=400, detail=f"Bad Request: {e}")
        except IOError as e:
            logging.error(f"IO-Fehler bei der Verarbeitung: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
        except Exception as e:
            logging.error(f"Unerwarteter Fehler bei der Verarbeitung: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal Server Error: unexpected error")

    return app