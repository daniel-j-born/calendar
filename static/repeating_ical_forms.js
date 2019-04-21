function addEvent() {
    var num_events = document.getElementById("num_events");
    var container = document.getElementById("events");
    ++num_events.value;
    var tr = document.createElement("tr");

    var summary_td = document.createElement("td");
    summary_td.className = "eventsummary";
    var summary_input = document.createElement("input");
    summary_input.name = "summary_" + (num_events.value - 1);
    summary_input.type = "text";
    summary_input.value = "Event " + num_events.value;
    summary_td.appendChild(summary_input);
    tr.appendChild(summary_td);

    var period_td = document.createElement("td");
    var period_input = document.createElement("input");
    period_input.name = "period_" + (num_events.value - 1);
    period_input.type = "text";
    period_input.value = "HH:MM";
    period_td.appendChild(period_input);

    var delete_button = document.createElement("input");
    delete_button.type = "button";
    delete_button.name = "delete_" + (num_events.value - 1);
    delete_button.id = "delete_" + (num_events.value - 1);
    delete_button.value = "Delete Event";
    delete_button.onclick = function() { container.removeChild(tr); };
    period_td.appendChild(delete_button);
    tr.appendChild(period_td);
    container.appendChild(tr);
}

function setDefaultStartEndTimes() {
    var start_time = document.getElementById("start_time");
    var end_time = document.getElementById("end_time");
    if (start_time.value || end_time.value) {
        return;
    }
    // Set start and end times to current time.
    var now = new Date();
    var hours_str;
    if (now.getHours() < 10) {
        hours_str = '0' + now.getHours();
    } else {
        hours_str = '' + now.getHours();
    }
    var minutes_str;
    if (now.getMinutes() < 10) {
        minutes_str = '0' + now.getMinutes();
    } else {
        minutes_str = '' + now.getMinutes();
    }
    var now_str = now.getFullYear() + '/' + (now.getMonth() + 1) + '/' +
      now.getDate() + ' ' + hours_str + ':' + minutes_str;
    start_time.value = now_str;
    end_time.value = now_str;
}

function formsOnload() {
    setDefaultStartEndTimes();

    // Process default states of alarm settings.
    updateAlarmInputsHidden();

    var num_events = document.getElementById("num_events");
    if (num_events.value == 0) {
        // Add first event.
        addEvent();
    }
}

function updateAlarmInputsHidden() {
    // Element ids of rows shown if set_alarms is checked.
    var alarm_row_ids = ["alarm_before_secs_row", "alarms_repeat_row"];
    // Element ids of rows shown if set_alarms and alarms_repeat are checked.
    var alarms_repeat_row_ids = ["alarm_repetitions_row",
                                 "alarm_repetition_delay_row"];
    var i;
    var set_alarms = document.getElementById("set_alarms");
    for (i = 0; i < alarm_row_ids.length; i++) {
        document.getElementById(alarm_row_ids[i]).hidden = !set_alarms.checked;
    }
    var alarms_repeat = document.getElementById("alarms_repeat");
    for (i = 0; i < alarms_repeat_row_ids.length; i++) {
        document.getElementById(alarms_repeat_row_ids[i]).hidden =
            !set_alarms.checked || !alarms_repeat.checked
    }
}
