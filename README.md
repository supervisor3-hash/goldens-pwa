# GOLDENS PRO V7 — WHATSAPP GRATIS

Esta versión no necesita Meta Developers, WATI ni una API de pago.

## Cómo funciona
1. El cliente reserva su cita.
2. Goldens guarda la cita en la base de datos.
3. El cliente ve un ticket de confirmación.
4. Puede tocar **Enviar reserva a Goldens por WhatsApp**.
5. En el panel administrador, cada cita tiene un botón **WhatsApp**.
6. Ese botón abre el chat del cliente con la confirmación ya escrita; solo hay que tocar **Enviar**.

## Configurar el número de Goldens en Windows
Antes de ejecutar el sistema, en CMD escriba:

```bat
set GOLDENS_WHATSAPP_NUMBER=506XXXXXXXX
python app.py
```

Reemplace `XXXXXXXX` por el número real de Goldens.

## Direcciones
Cliente: `http://127.0.0.1:5000`

Administrador: `http://127.0.0.1:5000/admin`

Usuario: `admin`
PIN inicial: `2026`

## Importante
La versión gratis no envía mensajes automáticamente: abre WhatsApp / WhatsApp Web con el mensaje listo. Para enviar, una persona toca **Enviar**.
