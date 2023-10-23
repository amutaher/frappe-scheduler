import frappe
from frappe import _
import datetime
import pytz
from frappe.desk.doctype.event.event import Event
from frappe.integrations.doctype.google_calendar.google_calendar import (
	get_google_calendar_object,
	get_conference_data,
	repeat_on_to_google_calendar_recurrence_rule,
	get_attendees,
	format_date_according_to_google_calendar,
	update_event_in_google_calendar
)
from googleapiclient.errors import HttpError
from frappe.utils import (
	add_days,
	add_to_date,
	get_datetime,
	get_request_site_address,
	get_system_timezone,
	get_weekdays,
	now_datetime,
	convert_utc_to_system_timezone,
	get_datetime_str,
	now,
)
from frappe_appointment.helpers.email import send_email_template_mail
from frappe_appointment.constants import (
	APPOINTMENT_GROUP,
	USER_APPOINTMENT_AVAILABILITY,
)
from frappe_appointment.frappe_appointment.doctype.appointment_group.appointment_group import (
	vaild_date,
)
import requests
import json


class EventOverride(Event):
	def before_insert(self):
		if not self.custom_appointment_group:
			return

		self.push_to_google_calendar = False
		self.appointment_group = frappe.get_doc(
			APPOINTMENT_GROUP, self.custom_appointment_group
		)
		self.send_meet_email()
		self.update_attendees_for_appointment_group()

	def send_meet_email(self):
		appointment_group = self.appointment_group

		if (
			appointment_group.meet_link
			and appointment_group.email_template
			and self.event_participants
			and self.custom_doctype_link_with_event
		):
			args = dict(
				appointment_group=self.appointment_group, event=self, metadata=self.event_info
			)

			send_doc_value = self.custom_doctype_link_with_event[0]
			send_doc = frappe.get_doc(
				send_doc_value.reference_doctype, send_doc_value.reference_docname
			)

			send_email_template_mail(
				send_doc,
				args,
				self.appointment_group.email_template,
				recipients=self.get_recipients_event(),
			)

	def get_recipients_event(self):
		if not self.event_participants:
			return []

		recipients = []

		for participant in self.event_participants:
			if participant.reference_doctype != USER_APPOINTMENT_AVAILABILITY:
				recipients.append(participant.email)

		return recipients

	def update_attendees_for_appointment_group(self):
		members = self.appointment_group.members

		for member in members:
			try:
				user = frappe.get_doc(
					{
						"idx": len(self.event_participants),
						"doctype": "Event Participants",
						"parent": self.name,
						"reference_doctype": USER_APPOINTMENT_AVAILABILITY,
						"reference_docname": member.user,
						"email": member.user,
						"parenttype": "Event",
						"parentfield": "event_participants",
					}
				)
				self.event_participants.append(user)
			except Exception as e:
				pass

	def handle_webhook(self, body):
		def datetime_serializer(obj):
			if isinstance(obj, datetime.datetime):
				return obj.isoformat()

		appointment_group = frappe.get_doc(APPOINTMENT_GROUP, self.custom_appointment_group)

		if not appointment_group.webhook:
			return True

		try:
			api_res = requests.post(
				appointment_group.webhook, data=json.dumps(body, default=datetime_serializer)
			).json()

			if not api_res:
				raise False

			return True

		except Exception as e:
			print(e)
			return False


def insert_event_in_google_calendar_attendees(doc, method=None):
	google_calendar, account = get_google_calendar_object(doc.google_calendar)

	if not account.push_to_google_calendar:
		return

	event = {
		"summary": doc.subject,
		"description": doc.description,
		"google_calendar_event": 1,
	}

	event.update(
		format_date_according_to_google_calendar(
			doc.all_day,
			get_datetime(doc.starts_on),
			get_datetime(doc.ends_on) if doc.ends_on else None,
		)
	)

	if doc.repeat_on:
		event.update({"recurrence": repeat_on_to_google_calendar_recurrence_rule(doc)})

	attendees = get_attendees(doc)

	if doc.custom_sync_participants_google_calendars:
		event.update({"attendees": update_attendees(attendees)})
	else:
		event.update({"attendees": attendees})

	conference_data_version = 0

	if doc.add_video_conferencing:
		event.update({"conferenceData": get_conference_data(doc)})
		conference_data_version = 1

	try:
		event = (
			google_calendar.events()
			.insert(
				calendarId=doc.google_calendar_id,
				body=event,
				conferenceDataVersion=conference_data_version,
				sendUpdates="all",
			)
			.execute()
		)

		frappe.db.set_value(
			"Event",
			doc.name,
			{
				"google_calendar_event_id": event.get("id"),
				"google_meet_link": event.get("hangoutLink"),
			},
			update_modified=False,
		)

		frappe.msgprint(_("Event Synced with Google Calendar."))

	except HttpError as err:
		frappe.throw(
			_(
				"Google Calendar - Could not insert event in Google Calendar {0}, error code {1}."
			).format(account.name, err.resp.status)
		)


def update_attendees(attendees: list) -> list:
	for user in attendees:
		user["responseStatus"] = "accepted"
		try:
			user["id"] = frappe.get_last_doc(
				doctype="Google Calendar", filters={"user": user["email"]}
			).google_calendar_id

		except Exception as e:
			pass
	return attendees


@frappe.whitelist(allow_guest=True)
def create_event_for_appointment_group(
	appointment_group_id: str,
	date: str,
	start_time: str,
	end_time: str,
	event_participants,
	**args,
):
	event_info = args
	reschedule= event_info.get('reschedule',False)
	appointment_group = frappe.get_last_doc(
		APPOINTMENT_GROUP, filters={"route": appointment_group_id}
	)

	if not event_info.get("subject"):
		event_info["subject"] = appointment_group.name + " " + now()

	if not vaild_date(get_datetime(date), appointment_group)["is_valid"]:
		return frappe.throw(_("Invalid Date"))

	members = appointment_group.members

	if len(members) <= 0:
		return frappe.throw(_("No Member found"))

	google_calendar = frappe.get_last_doc(
		doctype="Google Calendar", filters={"user": members[0].user}
	)

	google_calendar_api_obj, account = get_google_calendar_object(google_calendar.name)
	if reschedule:
		event = frappe.get_last_doc('Event',filters={'custom_appointment_group':appointment_group.name})
		event.starts_on = get_datetime_str(
			convert_utc_to_system_timezone(
				datetime.datetime.fromisoformat(start_time).replace(tzinfo=None)
			)
		)
		event.ends_on =get_datetime_str(
			convert_utc_to_system_timezone(
				datetime.datetime.fromisoformat(end_time).replace(tzinfo=None)
			)
		)		
		event.save(ignore_permissions=True)
		
		if not event.handle_webhook(
			{
				"event": event.as_dict(),
				"appointment_group": appointment_group.as_dict(),
				"metadata": event_info,
			}
		):
			return frappe.throw(_("Unable to Update an event"))
		update_event_in_google_calendar(event)
		return frappe.msgprint("Interview has been Re-Scheduled.")
	calendar_event = {
		"doctype": "Event",
		"subject": event_info.get("subject"),
		"description": event_info.get("description"),
		"starts_on": get_datetime_str(
			convert_utc_to_system_timezone(
				datetime.datetime.fromisoformat(start_time).replace(tzinfo=None)
			)
		),
		"ends_on": get_datetime_str(
			convert_utc_to_system_timezone(
				datetime.datetime.fromisoformat(end_time).replace(tzinfo=None)
			)
		),
		"sync_with_google_calendar": 1,
		"google_calendar": account.name,
		"google_calendar_id": account.google_calendar_id,
		"pulled_from_google_calendar": 1,
		"custom_sync_participants_google_calendars": 1,
		"event_participants": json.loads(event_participants),
		"custom_doctype_link_with_event": json.loads(
			event_info.get("custom_doctype_link_with_event", "[]")
		),
		"event_type": event_info.get("event_type", "Public"),
		"custom_appointment_group": appointment_group.name,
		"event_info": event_info,
	}

	event = frappe.get_doc(calendar_event)

	if not event.handle_webhook(
		{
			"event": event.as_dict(),
			"appointment_group": appointment_group.as_dict(),
			"metadata": event_info,
		}
	):
		return frappe.throw(_("Unable to create an event"))

	event.insert(ignore_permissions=True)

	frappe.db.commit()

	return _("Event has been created")
