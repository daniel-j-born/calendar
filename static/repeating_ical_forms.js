var events_table_body_id = "events_table_body";

/**
 * Configuration parameters. These are set by formsOnload(), which should
 * be called on page load.
 */
var summary_ph, period_ph, delete_val;

/**
 * Add an event to events_table_body_id.
 */
function addEvent() {
    // We create new input elements with ids of the form:
    //   "events-0-summary", "events-0-period"
    // The row containing them has an id of the form:
    //   "events-0-row"
    // The server will generate "-errors-row" rows, but client side JS
    // doesn't create these error rows.
    var events_table = document.getElementById(events_table_body_id);
    if (events_table == null) {
        return;
    }
    // Either a "-row" or "-errors-row". Parse the "events-<int>" basename to
    // get the next available event ID.
    var next_event_num = 0;
    if (events_table.lastElementChild != null &&
        events_table.lastElementChild.id != null) {
        var last_row_id = events_table.lastElementChild.id;
        var tmp = last_row_id.replace(/^events-/, "");
        if (tmp != last_row_id) {
            tmp = /^\d+/.exec(tmp);
            if (tmp != null) {
                next_event_num = parseInt(tmp) + 1;
            }
        }
    }
    var baseid = "events-" + next_event_num;
    var tr = document.createElement("tr");
    tr.id = baseid + "-row";
    var summary_td = document.createElement("td");
    summary_td.className = "eventsummary";
    var summary_input = document.createElement("input");
    summary_input.id = baseid + "-summary";
    summary_input.name = summary_input.id;
    summary_input.required = true;
    summary_input.type = "text";
    summary_input.placeholder = summary_ph;
    summary_td.appendChild(summary_input);
    tr.appendChild(summary_td);

    var period_td = document.createElement("td");
    var period_input = document.createElement("input");
    period_input.id = baseid + "-period";
    period_input.name = period_input.id;
    period_input.required = true;
    period_input.type = "text";
    period_input.value = "";
    period_input.placeholder = period_ph;
    period_td.appendChild(period_input);

    var delete_button = document.createElement("input");
    delete_button.id = baseid + "-delete";
    delete_button.name = delete_button.id;
    delete_button.type = "button";
    delete_button.value = delete_val || "Delete";
    delete_button.onclick = function() { events_table.removeChild(tr); };
    period_td.appendChild(delete_button);
    tr.appendChild(period_td);
    events_table.appendChild(tr);
}

/**
 * Delete an event with the given baseid.
 *
 * This is for events created in the HTML by the server. Events created by
 * addEvent() have an onclick lambda for deletion.
 */
function deleteEvent(baseid) {
    var events_table = document.getElementById(events_table_body_id);
    if (events_table == null) {
        return;
    }
    var input_row_id = baseid + "-row";
    var input_row = document.getElementById(input_row_id);
    if (input_row != null) {
        events_table.removeChild(input_row);
    }
    var error_row_id = baseid + "-errors-row";
    var error_row = document.getElementById(error_row_id);
    if (error_row != null) {
        events_table.removeChild(error_row);
    }
}

/**
 * Set the start and end times to the current time. This is generally called
 * once on page load.
 */
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

/**
 * Perform initial page setup.
 *
 * Generally called from page onload.
 */
function formsOnload(summary_ph_in, period_ph_in, delete_val_in) {
    summary_ph = summary_ph_in;
    period_ph = period_ph_in;
    delete_val = delete_val_in;

    setDefaultStartEndTimes();

    // Process default states of alarm settings.
    updateAlarmInputsHidden();

    // Add an event row if there are none.
    var events_table = document.getElementById(events_table_body_id);
    if (events_table != null && events_table.children.length == 0) {
        addEvent();
    }
}

/**
 * Control when certain UI elements are hidden or not, based on other UI
 * elements. For example, only show alarm parameters if alarms are enabled.
 */
function updateAlarmInputsHidden() {
    // Element ids of rows shown if set_alarms is checked.
    var set_alarms_input_id = "set_alarms";
    var alarm_row_ids = ["alarm_before_secs_row", "alarms_repeat_row"];
    // Element ids of rows shown if set_alarms and alarms_repeat are checked.
    var alarms_repeat_input_id = "alarms_repeat";
    var alarms_repeat_row_ids = ["alarm_repetitions_row",
                                 "alarm_repetition_delay_secs_row"];
    var i;
    var set_alarms = document.getElementById(set_alarms_input_id);
    if (set_alarms) {
        for (i = 0; i < alarm_row_ids.length; i++) {
            document.getElementById(alarm_row_ids[i]).hidden = !set_alarms.checked;
        }
    }
    var alarms_repeat = document.getElementById(alarms_repeat_input_id);
    if (set_alarms && alarms_repeat) {
        for (i = 0; i < alarms_repeat_row_ids.length; i++) {
            document.getElementById(alarms_repeat_row_ids[i]).hidden =
                !set_alarms.checked || !alarms_repeat.checked
        }
    }
}
