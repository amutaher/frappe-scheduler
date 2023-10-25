# Copyright (c) 2023, rtCamp and contributors
# For license information, please see license.txt

import frappe
from frappe.website.website_generator import WebsiteGenerator
from frappe_appointment.constants import APPOINTMENT_GROUP, APPOINTMENT_TIME_SLOT
from frappe_appointment.frappe_appointment.doctype.appointment_time_slot.appointment_time_slot import (
	get_all_unavailable_google_calendar_slots_for_day,
	get_utc_datatime_with_time,
	convert_timezone_to_utc,
	convert_datetime_to_utc,
)
from dateutil import parser
from frappe.utils import (
	getdate,
	get_time_str,
	format_time,
	add_to_date,
	now_datetime,
	add_days,
	get_datetime,
	get_date_str,
	get_datetime_str,
)
import datetime


weekdays = [
	"Monday",
	"Tuesday",
	"Wednesday",
	"Thursday",
	"Friday",
	"Saturday",
	"Sunday",
]


class AppointmentGroup(WebsiteGenerator):
	website = frappe._dict(
		page_title_field="group_name",
		no_cache=1,
		no_breadcrumbs=1,
	)

	def validate(self):
		if not self.route:
			self.route = frappe.scrub(self.group_name).replace("_", "-")

	def get_context(self, context):
		return context


def get_list_context(context):
	return frappe.redirect("/")


@frappe.whitelist(allow_guest=True)
def get_time_slots_for_day(appointment_group_id: str, date: str) -> object:
	try:
		if not appointment_group_id:
			return {"result": []}

		appointment_group = frappe.get_last_doc(
			APPOINTMENT_GROUP, filters={"route": appointment_group_id}
		)

		datetime = get_datetime(date)
		date = datetime.date()
		weekday = weekdays[date.weekday()]

		date_validation_obj = vaild_date(datetime, appointment_group)


		if not date_validation_obj["is_valid"] or not check_weekend_avalability(
			appointment_group.enable_scheduling_on_weekends, weekday
		):
			return {
				"appointment_group_id": appointment_group_id,
				"valid_start_date": date_validation_obj["valid_start_date"],
				"valid_end_date": date_validation_obj["valid_end_date"],
				"total_slots_for_day": 0,
				"is_invalid_date": True,
				"enable_scheduling_on_weekends": appointment_group.enable_scheduling_on_weekends,
			}

		booking_frequency_reached_obj = get_booking_frequency_reached(
			datetime, appointment_group
		)

		if not booking_frequency_reached_obj["is_slots_available"]:
			return {
				"all_avaiable_slots_for_data": [],
				"date": date,
				"duration": appointment_group.duration_for_event,
				"appointment_group_id": appointment_group_id,
				"total_slots_for_day": 0,
				"valid_start_date": date_validation_obj["valid_start_date"],
				"valid_end_date": date_validation_obj["valid_end_date"],
				"enable_scheduling_on_weekends": appointment_group.enable_scheduling_on_weekends,
			}

		members = appointment_group.members

		member_time_slots = {}
		max_start_time, min_end_time = "00:00:00", "24:00:00"

		for member in members:
			if not member.is_mandatory:
				continue

			appointmen_time_slots = frappe.db.get_all(
				APPOINTMENT_TIME_SLOT, filters={"parent": member.user, "day": weekday}, fields="*"
			)

			max_start_time, min_end_time = get_max_min_time_slot(
				appointmen_time_slots, max_start_time, min_end_time
			)

			member_time_slots[member.user] = appointmen_time_slots

		starttime = get_utc_datatime_with_time(date, max_start_time)
		endtime = get_utc_datatime_with_time(date, min_end_time)

		all_slots = get_all_unavailable_google_calendar_slots_for_day(
			member_time_slots, starttime, endtime, date
		)

		all_slots = update_cal_slots_with_events(
			all_slots, booking_frequency_reached_obj["events"]
		)

		avaiable_time_slot_for_day = get_avaiable_time_slot_for_day(
			all_slots, starttime, endtime, appointment_group
		)

		return {
			"all_avaiable_slots_for_data": avaiable_time_slot_for_day,
			"date": date,
			"duration": appointment_group.duration_for_event,
			"appointment_group_id": appointment_group_id,
			"starttime": starttime,
			"endtime": endtime,
			"total_slots_for_day": len(avaiable_time_slot_for_day),
			"valid_start_date": date_validation_obj["valid_start_date"],
			"valid_end_date": date_validation_obj["valid_end_date"],
			"enable_scheduling_on_weekends": appointment_group.enable_scheduling_on_weekends,
		}
	except Exception as e:
		# raise Exception(e)
		return None


def check_weekend_avalability(enable_scheduling_on_weekends: bool, weekday: str):
	if enable_scheduling_on_weekends:
		return True
	return not (weekday == "Saturday" or weekday == "Sunday")


def get_booking_frequency_reached(
	datetime: datetime, appointment_group: object
) -> bool:
	if int(appointment_group.limit_booking_frequency) < 0:
		return {
			"is_slots_available": True,
			"events": [],
		}

	start_datetime, end_datetime = get_datetime_str(datetime), get_datetime_str(
		add_days(datetime, 1)
	)

	all_events = frappe.get_list(
		"Event",
		filters=[
			["custom_appointment_group", "=", appointment_group.name],
			["starts_on", ">=", start_datetime],
			["starts_on", "<", end_datetime],
			["ends_on", ">=", start_datetime],
			["ends_on", "<", end_datetime],
		],
		fields=["starts_on", "ends_on"],
		order_by="starts_on asc",
	)

	all_events = sorted(
		all_events,
		key=lambda slot: get_datetime_str(slot["ends_on"]),
	)

	return {
		"is_slots_available": len(all_events)
		< int(appointment_group.limit_booking_frequency),
		"events": all_events,
	}


def vaild_date(date: datetime, appointment_group: object) -> bool:
	current_date = get_datetime(now_datetime().date())

	start_date = add_days(current_date, int(appointment_group.minimum_notice_before_event))
	end_date = add_days(start_date, int(appointment_group.event_availability_window))

	if start_date > date:
		return {"is_valid": False, "valid_start_date": start_date, "valid_end_date": end_date}

	if int(appointment_group.event_availability_window) > 0 and end_date < date:
		return {"is_valid": False, "valid_start_date": start_date, "valid_end_date": end_date}

	if int(appointment_group.event_availability_window) <= 0:
		end_date = ""

	return {"is_valid": True, "valid_start_date": start_date, "valid_end_date": end_date}


def update_cal_slots_with_events(all_slots: list, all_events: list) -> list:
	update_slots = []
	for currernt_slot in all_slots:
		updated_slot = {}
		updated_slot["is_frappe_event"] = False
		updated_slot["starts_on"] = convert_timezone_to_utc(
			currernt_slot["start"]["dateTime"], currernt_slot["start"]["timeZone"]
		)
		updated_slot["ends_on"] = convert_timezone_to_utc(
			currernt_slot["end"]["dateTime"], currernt_slot["end"]["timeZone"]
		)
		for event in all_events:

			if convert_datetime_to_utc(event["starts_on"]) == updated_slot[
				"starts_on"
			] and updated_slot["ends_on"] == convert_datetime_to_utc(event["ends_on"]):
				updated_slot["is_frappe_event"] = True
				break

		update_slots.append(updated_slot)

	return update_slots


def get_avaiable_time_slot_for_day(
	all_slots: list, starttime: datetime, endtime: datetime, appointment_group: object
) -> list:
	available_slots = []

	index = 0

	minimum_buffer_time = appointment_group.minimum_buffer_time
	current_start_time = get_next_round_value(minimum_buffer_time, starttime, False)

	minute, second = divmod(appointment_group.duration_for_event.seconds, 60)
	hour, minute = divmod(minute, 60)

	current_end_time = add_to_date(
		current_start_time, hours=hour, minutes=minute, seconds=second
	)

	while current_end_time <= endtime:

		if index >= len(all_slots) and current_end_time <= endtime:
			available_slots.append(
				{"start_time": current_start_time, "end_time": current_end_time}
			)
			current_start_time = get_next_round_value(minimum_buffer_time, current_end_time)
			current_end_time = add_to_date(
				current_start_time, hours=hour, minutes=minute, seconds=second
			)
			continue

		currernt_slot = all_slots[index]
		currernt_slot_start_time = currernt_slot["starts_on"]
		currernt_slot_end_time = currernt_slot["ends_on"]

		if current_end_time <= currernt_slot_start_time and is_valid_buffer_time(
			minimum_buffer_time,
			current_end_time,
			currernt_slot_start_time,
			currernt_slot["is_frappe_event"],
		):
			available_slots.append(
				{"start_time": current_start_time, "end_time": current_end_time}
			)
			current_start_time = get_next_round_value(minimum_buffer_time, current_end_time)
		else:
			current_start_time = get_next_round_value(
				minimum_buffer_time, currernt_slot_end_time, currernt_slot["is_frappe_event"]
			)
			index += 1

		current_end_time = add_to_date(
			current_start_time, hours=hour, minutes=minute, seconds=second
		)

	return available_slots


def is_valid_buffer_time(
	minimum_buffer_time: datetime,
	end: datetime,
	next_start: datetime,
	is_add_buffer_in_event: bool = True,
):
	if not minimum_buffer_time or not is_add_buffer_in_event:
		return True

	return minimum_buffer_time.seconds <= (next_start - end).seconds


def get_next_round_value(
	minimum_buffer_time: datetime,
	current_start_time: datetime,
	is_add_buffer_in_event: bool = True,
):
	if not minimum_buffer_time or not is_add_buffer_in_event:
		return current_start_time

	minute, second = divmod(minimum_buffer_time.seconds, 60)
	hour, minute = divmod(minute, 60)

	min_start_time = add_to_date(
		current_start_time, hours=hour, minutes=minute, seconds=second
	)

	return min_start_time


def get_max_min_time_slot(
	appointmen_time_slots: list, max_start_time: str, min_end_time: str
) -> list:

	for appointmen_time_slot in appointmen_time_slots:
		max_start_time = max(
			max_start_time, format_time(get_time_str(appointmen_time_slot.start_time))
		)
		min_end_time = min(
			min_end_time, format_time(get_time_str(appointmen_time_slot.end_time))
		)

	return [max_start_time, min_end_time]
