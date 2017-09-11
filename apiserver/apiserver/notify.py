import collections
import itertools

import sendgrid
import sendgrid.helpers
import sendgrid.helpers.mail

from . import config


sg = sendgrid.SendGridAPIClient(apikey=config.SENDGRID_API_KEY)


Recipient = collections.namedtuple("Recipient", [
    "user_id",
    "username",
    "email",
    "organization",
    "level",
    "date_created",
])


def send_notification(recipient_email, recipient_name, subject, body,
                      attachments=None):
    mail = sendgrid.helpers.mail.Mail()

    mail.from_email = sendgrid.Email("halite@halite.io", "Halite Challenge")
    personalization = sendgrid.helpers.mail.Personalization()
    personalization.add_to(sendgrid.helpers.mail.Email(recipient_email, recipient_name))
    personalization.subject = "Halite Challenge: " + subject
    mail.add_personalization(personalization)

    mail.add_content(sendgrid.helpers.mail.Content("text/html", body))

    settings = sendgrid.helpers.mail.MailSettings()
    settings.sandbox_mode = sendgrid.helpers.mail.SandBoxMode(config.SENDGRID_SANDBOX_MODE)
    mail.mail_settings = settings

    response = sg.client.mail.send.post(request_body=mail.get())
    print(response.status_code)
    print(response.headers)
    print(response.body)


def send_templated_notification(recipient, template_id, substitutions, group_id):
    """
    Send an email based on a template.
    :param Recipient recipient: The recipient of the email
    :param str template_id: The template ID of the email.
    :param Dict[str, Any] substitutions: Any other substitution variables to
    pass to the email template.
    """
    mail = sendgrid.helpers.mail.Mail()

    if not recipient.organization:
        recipient.organization = "(no affiliation)"

    mail.from_email = sendgrid.Email("halite@halite.io", "Halite Challenge")
    personalization = sendgrid.helpers.mail.Personalization()
    personalization.add_to(sendgrid.helpers.mail.Email(recipient.email, recipient.username))

    all_substitutions = itertools.chain(
        recipient._asdict().items(), substitutions.items())
    for substitution_key, substitution_value in all_substitutions:
        personalization.add_substitution(sendgrid.helpers.mail.Substitution(
            "-{}-".format(substitution_key), substitution_value))

    mail.add_personalization(personalization)
    mail.template_id = template_id
    mail.asm = sendgrid.helpers.mail.ASM(group_id, [10307, 10445, 10445, 10447, 10449])
    settings = sendgrid.helpers.mail.MailSettings()
    settings.sandbox_mode = sendgrid.helpers.mail.SandBoxMode(config.SENDGRID_SANDBOX_MODE)
    mail.mail_settings = settings

    sg.client.mail.send.post(request_body=mail.get())

