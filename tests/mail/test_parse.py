"""MIME decoding and quote stripping on synthetic Gmail and Outlook samples."""

import base64
from email.message import EmailMessage

from app.mail.parse import (
    extract_text,
    mail_message_from_gmail,
    mail_message_from_raw,
    sha256_text,
)

GMAIL_PLAIN = (
    "Thanks. The line ending 4417 stays as requested.\n"
    "\n"
    "On Mon, 16 Oct 2026 at 09:00, Sara Malik <sara.malik@family.example> wrote:\n"
    "> Please keep the number and the voicemail.\n"
    "> Ref AW-1042-1\n"
)

GMAIL_WRAPPED = (
    "Confirmed.\n"
    "\n"
    "On Mon, 16 Oct 2026 at 09:00, Sara Malik <\n"
    "sara.malik@family.example> wrote:\n"
    "> Older text.\n"
)

OUTLOOK_PLAIN = (
    "We have received your request.\n"
    "\n"
    "________________________________\n"
    "From: Sara Malik <sara.malik@family.example>\n"
    "Sent: Monday, October 16, 2026 9:00 AM\n"
    "To: bereavement@northline.example\n"
    "Subject: Line ending 4417\n"
    "\n"
    "Please keep the number and the voicemail.\n"
)

HTML_ONLY = (
    "<html><body>"
    "<p>Request complete. Line transferred.</p>"
    '<div class="gmail_quote">'
    "On Mon, 16 Oct 2026 at 09:00, Sara Malik &lt;sara.malik@family.example&gt; wrote:<br>"
    "<blockquote>Please keep the number.</blockquote>"
    "</div></body></html>"
)


def test_gmail_quotes_and_on_wrote_blocks_are_stripped_and_hashed():
    extracted = extract_text(GMAIL_PLAIN)
    assert extracted.latest_text == "Thanks. The line ending 4417 stays as requested."
    assert "Please keep the number" not in extracted.latest_text
    assert extracted.remainder_sha256 == sha256_text(extracted.latest_text)
    assert extracted.full_sha256 == sha256_text(GMAIL_PLAIN)
    assert extracted.quoted_sha256 == sha256_text(
        "On Mon, 16 Oct 2026 at 09:00, Sara Malik <sara.malik@family.example> wrote:\n"
        "> Please keep the number and the voicemail.\n"
        "> Ref AW-1042-1"
    )


def test_wrapped_gmail_attribution_is_stripped():
    extracted = extract_text(GMAIL_WRAPPED)
    assert extracted.latest_text == "Confirmed."
    assert "Older text" not in extracted.latest_text


def test_outlook_header_block_is_stripped():
    extracted = extract_text(OUTLOOK_PLAIN)
    assert extracted.latest_text == "We have received your request."
    assert "Please keep the number" not in extracted.latest_text
    assert "From: Sara Malik" not in extracted.latest_text


def test_inline_comparison_and_ordinary_on_sentence_stay():
    text = "The balance was cost > 10.\nOn Monday the team wrote a note."
    extracted = extract_text(text)
    assert extracted.latest_text == text
    assert extracted.quoted_sha256 == sha256_text("")


def test_original_message_separator_is_stripped():
    text = "Acknowledged.\n\n-----Original Message-----\nFrom: sara.malik@family.example\n"
    assert extract_text(text).latest_text == "Acknowledged."


def test_multipart_mime_prefers_plain_and_strips_quotes():
    message = EmailMessage()
    message["From"] = '"Northline Mobile (demo)" <bereavement@northline.example>'
    message["To"] = "family.demo@example.com"
    message["Subject"] = "Re: Line ending 4417"
    message["Message-ID"] = "<plain@providers.example>"
    message["In-Reply-To"] = "<sent-1@afterward.example>"
    message["References"] = "<sent-1@afterward.example>"
    message.set_content(GMAIL_PLAIN)
    message.add_alternative("<p>HTML should not win</p>", subtype="html")
    decoded = mail_message_from_raw(
        mailbox="family.demo@example.com",
        gmail_id="g-1",
        thread_id="thread-1",
        raw=message.as_bytes(),
    )
    assert decoded.latest_text == "Thanks. The line ending 4417 stays as requested."
    assert decoded.from_addr == "bereavement@northline.example"
    assert decoded.from_name == "Northline Mobile (demo)"
    assert decoded.references == ["<sent-1@afterward.example>"]
    assert "HTML should not win" not in decoded.full_text


def test_html_only_mime_drops_the_gmail_quote():
    message = EmailMessage()
    message["From"] = '"City Power (demo)" <accounts@citypower.example>'
    message["To"] = "family.demo@example.com"
    message["Subject"] = "Invoice"
    message["Message-ID"] = "<html@providers.example>"
    message.set_content(HTML_ONLY, subtype="html")
    decoded = mail_message_from_raw(
        mailbox="family.demo@example.com",
        gmail_id="g-html",
        thread_id="thread-html",
        raw=message.as_bytes(),
    )
    assert decoded.latest_text == "Request complete. Line transferred."
    assert "Please keep the number" not in decoded.latest_text


def test_gmail_full_resource_decodes_plain_text():
    data = base64.urlsafe_b64encode(GMAIL_PLAIN.encode()).decode().rstrip("=")
    resource = {
        "id": "g-res",
        "threadId": "thread-res",
        "internalDate": "1760630400000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {
                    "name": "From",
                    "value": "Northline Mobile (demo) <bereavement@northline.example>",
                },
                {"name": "To", "value": "family.demo@example.com"},
                {"name": "Subject", "value": "Re: Line ending 4417"},
                {"name": "Message-ID", "value": "<g-res@providers.example>"},
                {"name": "Reply-To", "value": "notices@northline-mail.example"},
            ],
            "body": {"data": data},
        },
    }
    decoded = mail_message_from_gmail("family.demo@example.com", resource)
    assert decoded.gmail_id == "g-res"
    assert decoded.latest_text == "Thanks. The line ending 4417 stays as requested."
    assert decoded.reply_to == "notices@northline-mail.example"
    assert decoded.received_at.tzinfo is not None
