/**
 * External dependencies.
 */
import { useEffect, useRef, useState } from "react";
import { format, formatDate } from "date-fns";
import {
  Clock,
  Calendar as CalendarIcon,
  ArrowLeft,
  Tag,
  CircleAlert,
} from "lucide-react";
import { useFrappeGetCall, useFrappePostCall } from "frappe-react-sdk";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

/**
 * Internal dependencies.
 */
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { type TimeFormat, type MeetingData } from "../types";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import Typography from "@/components/ui/typography";
import {
  cn,
  convertToMinutes,
  getAllSupportedTimeZones,
  getTimeZoneOffsetFromTimeZoneString,
  parseDateString,
  parseFrappeErrorMsg,
} from "@/lib/utils";
import MeetingForm from "./meetingForm";
import { useAppContext } from "@/context/app";
import TimeSlotSkeleton from "./timeSlotSkeleton";
import TimeZoneSelect from "./timeZoneSelectmenu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import Spinner from "@/components/ui/spinner";
import useBack from "@/hooks/useBack";
import SuccessAlert from "@/components/successAlert";
import { BookingResponseType } from "@/lib/types";
import { Icon } from "@/components/icons";
import { CalendarWrapper } from "@/components/calendarWrapper";

interface BookingProp {
  type: string;
}

const Booking = ({ type }: BookingProp) => {
  const {
    userInfo,
    timeZone,
    duration,
    setDuration,
    setTimeZone,
    selectedDate,
    setSelectedDate,
    selectedSlot,
    setSelectedSlot,
    meetingId,
  } = useAppContext();
  const [timeFormat, setTimeFormat] = useState<TimeFormat>("12h");
  const containerRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [isMobileView, setIsMobileView] = useState(false);
  const [showMeetingForm, setShowMeetingForm] = useState(false);
  const [showReschedule, setShowReschedule] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const [appointmentScheduled, setAppointmentScheduled] = useState(false);
  const [bookingResponse, setBookingResponse] = useState<BookingResponseType>({
    event_id: "",
    meet_link: "",
    meeting_provider: "",
    message: "",
    reschedule_url: "",
    google_calendar_event_url: "",
  });
  const location = useLocation();

  const date = searchParams.get("date");
  const reschedule = searchParams.get("reschedule") || "";
  const event_token = searchParams.get("event_token") || "";
  const [displayMonth, setDisplayMonth] = useState(parseDateString(date || ""));

  const handleBackNavigation = () => {
    navigate(location.pathname, { replace: true });
  };

  useBack(handleBackNavigation);

  useEffect(() => {
    if (date) {
      setSelectedDate(parseDateString(date));
    }
  }, [date]);

  const updateDateQuery = (date: Date) => {
    const queries: Record<string, string> = {};
    searchParams.forEach((value, key) => (queries[key] = value));
    setSearchParams({
      ...queries,
      date: `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`,
      type,
    });
  };

  const [meetingData, setMeetingData] = useState<MeetingData>({
    all_available_slots_for_data: [],
    available_days: [],
    date: "",
    duration: "",
    endtime: "",
    is_invalid_date: true,
    next_valid_date: "",
    prev_valid_date: "",
    starttime: "",
    total_slots_for_day: 0,
    user: "",
    valid_end_date: "",
    valid_start_date: "",
    label: "",
  });
  const navigate = useNavigate();
  const { data, isLoading, error, mutate } = useFrappeGetCall(
    "frappe_appointment.api.personal_meet.get_time_slots",
    {
      duration_id: type,
      date: new Intl.DateTimeFormat("en-CA", {
        year: "numeric",
        month: "numeric",
        day: "numeric",
      }).format(date ? parseDateString(date) : selectedDate),
      user_timezone_offset: String(
        getTimeZoneOffsetFromTimeZoneString(timeZone || "Asia/Calcutta")
      ),
    },
    undefined,
    {
      revalidateOnFocus: false,
    }
  );
  const { call: rescheduleMeeting, loading: rescheduleLoading } =
    useFrappePostCall("frappe_appointment.api.personal_meet.book_time_slot");

  const onReschedule = () => {
    const extraArgs: Record<string, string> = {};
    searchParams.forEach((value, key) => (extraArgs[key] = value));

    const meetingData = {
      duration_id: type,
      date: new Intl.DateTimeFormat("en-CA", {
        year: "numeric",
        month: "numeric",
        day: "numeric",
      }).format(selectedDate),
      user_timezone_offset: String(
        getTimeZoneOffsetFromTimeZoneString(timeZone)
      ),
      start_time: selectedSlot.start_time,
      end_time: selectedSlot.end_time,
      user_name: "",
      user_email: "",
      other_participants: "",
      reschedule,
      event_token,
      ...extraArgs,
    };

    rescheduleMeeting(meetingData)
      .then((data) => {
        setShowMeetingForm(false);
        setExpanded(false);
        mutate();
        setBookingResponse(data.message);
        setAppointmentScheduled(true);
      })
      .catch((err) => {
        const error = parseFrappeErrorMsg(err);
        toast(error || "Something went wrong", {
          duration: 4000,
          classNames: {
            actionButton:
              "group-[.toast]:!bg-red-500 group-[.toast]:hover:!bg-red-300 group-[.toast]:!text-white",
          },
          icon: <CircleAlert className="h-5 w-5 text-red-500" />,
          action: {
            label: "OK",
            onClick: () => toast.dismiss(),
          },
        });
      });
  };

  useEffect(() => {
    if (data) {
      setMeetingData(data.message);
      setDuration(convertToMinutes(data?.message?.duration).toString());
      const validData = data.message.is_invalid_date
        ? new Date(data.message.next_valid_date)
        : selectedDate;
      setSelectedDate(validData);
      updateDateQuery(validData);
      setDisplayMonth(validData);
    }
    if (error) {
      const err = parseFrappeErrorMsg(error);
      toast(err || "Something went wrong", {
        duration: 4000,
        classNames: {
          actionButton:
            "group-[.toast]:!bg-red-500 group-[.toast]:hover:!bg-red-300 group-[.toast]:!text-white",
        },
        icon: <CircleAlert className="h-5 w-5 text-red-500" />,
        action: {
          label: "OK",
          onClick: () => toast.dismiss(),
        },
      });
    }
  }, [data, error, type, navigate, setDuration, setMeetingData, mutate]);

  const formatTimeSlot = (date: Date) => {
    return new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "numeric",
      hour12: timeFormat === "12h",
      timeZone,
    }).format(date);
  };

  useEffect(() => {
    const handleResize = () => {
      setIsMobileView(window.innerWidth <= 768);
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (containerRef.current && isMobileView) {
      containerRef.current.style.width = "100%";
    }
  }, [isMobileView]);

  return (
    <>
      <div className="w-full h-fit flex justify-center">
        <div className="md:w-4xl max-lg:w-full py-8 p-4 md:py-16 gap-10 md:gap-12">
          <div className="w-full rounded-lg flex max-lg:flex-col md:border gap-8 md:gap-28 items-start">
            {/* Profile */}
            <div className="w-full md:max-w-sm flex flex-col gap-4 md:p-6 md:px-4">
              <Avatar className="md:h-32 md:w-32 h-24 w-24 object-cover mb-4 md:mb-0 ">
                <AvatarImage
                  src={userInfo.userImage}
                  alt="Profile picture"
                  className="bg-blue-50"
                />
                <AvatarFallback className="text-4xl">
                  {userInfo.name?.toString()[0]?.toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <div className="w-full flex flex-col gap-1">
                <Typography variant="h2" className="text-3xl font-semibold">
                  <Tooltip>
                    <TooltipTrigger className="w-full truncate text-left">
                      {userInfo.name}
                    </TooltipTrigger>
                    <TooltipContent>{userInfo.name}</TooltipContent>
                  </Tooltip>
                </Typography>
                {userInfo.designation && userInfo.organizationName && (
                  <Typography className="text-base text-muted-foreground">
                    {userInfo.designation} at {userInfo.organizationName}
                  </Typography>
                )}
                {meetingData.label ? (
                  <Typography className="text-sm mt-1">
                    <Tag className="inline-block w-4 h-4 mr-1" />
                    {meetingData.label}
                  </Typography>
                ) : (
                  <Skeleton className="h-5 w-20" />
                )}
                {duration ? (
                  <Typography className="text-sm mt-1">
                    <Clock className="inline-block w-4 h-4 mr-1" />
                    {duration} Minute Meeting
                  </Typography>
                ) : (
                  <Skeleton className="h-5 w-24" />
                )}
                <Typography className="text-sm  mt-1">
                  <CalendarIcon className="inline-block w-4 h-4 mr-1" />
                  {formatDate(new Date(), "d MMM, yyyy")}
                </Typography>
                {userInfo.meetingProvider.toLowerCase() == "zoom" && (
                  <Typography className="text-sm text-blue-500 mt-1 flex items-center">
                    <Icon name="zoom" />
                    Zoom
                  </Typography>
                )}{" "}
                {userInfo.meetingProvider.toLowerCase() == "google meet" && (
                  <Typography className="text-sm text-blue-700 mt-1 flex items-center">
                    <Icon name="googleMeet" />
                    Google Meet
                  </Typography>
                )}
              </div>
            </div>
            {/* Calendar and Availability slots */}
            {!showMeetingForm && (
              <div className="w-full flex max-lg:flex-col gap-4 md:p-6 pb-5">
                {(!isMobileView || !expanded) && (
                  <div className="flex flex-col w-full lg:w-[25rem] shrink-0">
                    <CalendarWrapper
                      displayMonth={displayMonth}
                      selectedDate={selectedDate}
                      loading={rescheduleLoading}
                      setDisplayMonth={setDisplayMonth}
                      meetingData={{
                        valid_start_date: meetingData.valid_start_date,
                        valid_end_date: meetingData.valid_end_date,
                        available_days: meetingData.available_days,
                      }}
                      setSelectedDate={setSelectedDate}
                      onDayClick={(date) => {
                        setSelectedDate(date);
                        updateDateQuery(date);
                        setDisplayMonth(date);
                        setExpanded(true);
                        setShowReschedule(false);
                        setSelectedSlot({
                          start_time: "",
                          end_time: "",
                        });
                      }}
                      className="rounded-md md:border md:h-96 w-full flex md:px-6 p-0"
                    />
                    <div className="mt-4  gap-5 flex max-md:flex-col md:justify-between md:items-center ">
                      {/* Timezone */}

                      <TimeZoneSelect
                        timeZones={getAllSupportedTimeZones()}
                        setTimeZone={setTimeZone}
                        timeZone={timeZone}
                      />

                      {/* Time Format Toggle */}
                      <div className="flex items-center gap-2">
                        <Typography className="text-sm text-gray-700">
                          AM/PM
                        </Typography>
                        <Switch
                          disabled={rescheduleLoading}
                          className="data-[state=checked]:bg-blue-500 active:ring-blue-400 focus-visible:ring-blue-400"
                          checked={timeFormat === "24h"}
                          onCheckedChange={(checked) =>
                            setTimeFormat(checked ? "24h" : "12h")
                          }
                        />
                        <Typography className="text-sm text-gray-700">
                          24H
                        </Typography>
                      </div>
                    </div>
                  </div>
                )}

                {/* Availability Slots */}
                {isMobileView && expanded && (
                  <div className="h-14 fixed bottom-0 left-0 w-screen border z-10 bg-white border-top flex items-center justify-between px-4">
                    <Button
                      variant="link"
                      className="text-blue-500 px-0"
                      onClick={() => setExpanded(false)}
                      disabled={rescheduleLoading}
                    >
                      <ArrowLeft className="h-4 w-4" />
                      Back
                    </Button>
                    {showReschedule && (
                      <Button
                        className="bg-blue-400 hover:bg-blue-500 w-fit px-6"
                        onClick={onReschedule}
                        disabled={rescheduleLoading || !showReschedule}
                      >
                        {rescheduleLoading && <Spinner />} Reschedule
                      </Button>
                    )}
                  </div>
                )}

                {/* Available slots */}
                <div
                  className={cn(
                    "w-48 max-lg:w-full overflow-hidden space-y-4 max-md:pb-10  transition-all duration-300 ",
                    !expanded && "max-md:hidden",
                    showReschedule && "lg:flex lg:flex-col lg:justify-between"
                  )}
                >
                  <h3 className="text-sm font-semibold lg:w-full">
                    {format(selectedDate, "EEEE, d MMMM yyyy")}
                  </h3>
                  {isLoading ? (
                    <TimeSlotSkeleton />
                  ) : (
                    <div
                      className={cn(
                        "lg:h-[22rem] overflow-y-auto no-scrollbar space-y-2 transition-transform transform",
                        showReschedule && "lg:!mt-0"
                      )}
                      style={{
                        transform: selectedDate
                          ? "translateX(0)"
                          : "translateX(-100%)",
                      }}
                    >
                      {meetingData.all_available_slots_for_data.length > 0 ? (
                        meetingData.all_available_slots_for_data.map(
                          (slot, index) => (
                            <Button
                              disabled={rescheduleLoading}
                              key={index}
                              onClick={() => {
                                if (reschedule && event_token) {
                                  setShowReschedule(true);
                                } else {
                                  setShowMeetingForm(true);
                                }
                                setSelectedSlot({
                                  start_time: slot.start_time,
                                  end_time: slot.end_time,
                                });
                              }}
                              variant="outline"
                              className={cn(
                                "w-full font-normal border border-blue-500 text-blue-500 hover:text-blue-500 hover:bg-blue-50 transition-colors ",
                                selectedSlot.start_time === slot.start_time &&
                                  selectedSlot.end_time === slot.end_time &&
                                  reschedule &&
                                  event_token &&
                                  "bg-blue-500 text-white hover:bg-blue-400 hover:text-white"
                              )}
                            >
                              {formatTimeSlot(new Date(slot.start_time))}
                            </Button>
                          )
                        )
                      ) : (
                        <div className="h-full max-md:h-44 w-full flex justify-center items-center">
                          <Typography className="text-center text-gray-500">
                            No open-time slots
                          </Typography>
                        </div>
                      )}
                    </div>
                  )}
                  {showReschedule && (
                    <Button
                      className="bg-blue-400 hover:bg-blue-500 lg:!mt-0 max-lg:w-full max-md:hidden"
                      onClick={onReschedule}
                      disabled={rescheduleLoading}
                    >
                      {rescheduleLoading && <Spinner />} Reschedule
                    </Button>
                  )}
                </div>
              </div>
            )}
            {showMeetingForm && (
              <MeetingForm
                onSuccess={(data) => {
                  setShowMeetingForm(false);
                  setExpanded(false);
                  mutate();
                  setBookingResponse(data.message);
                  setAppointmentScheduled(true);
                }}
                onBack={() => {
                  setShowMeetingForm(false);
                  setExpanded(false);
                  mutate();
                }}
                durationId={type}
              />
            )}
          </div>
        </div>
      </div>
      {selectedSlot?.start_time && (
        <SuccessAlert
          open={appointmentScheduled}
          setOpen={setAppointmentScheduled}
          selectedSlot={selectedSlot}
          onClose={() => {
            navigate(`/in/${meetingId}`);
          }}
          meetingProvider={bookingResponse.meeting_provider}
          meetLink={bookingResponse.meet_link}
          rescheduleLink={bookingResponse.reschedule_url}
          calendarString={bookingResponse.google_calendar_event_url}
        />
      )}
    </>
  );
};

export default Booking;
