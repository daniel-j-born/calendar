function addEvent() {
    var num_events = document.getElementById("num_events");
    var container = document.getElementById("events");
    ++num_events.value;
    var tr = document.createElement("tr");

    var summary_td = document.createElement("td");
    var summary_input = document.createElement("input");
    summary_input.name = "summary_" + (num_events.value - 1);
    summary_input.type = "text";
    summary_td.appendChild(summary_input);
    tr.appendChild(summary_td);

    var period_td = document.createElement("td");
    var period_input = document.createElement("input");
    period_input.name = "period_" + (num_events.value - 1);
    period_input.type = "text";
    period_td.appendChild(period_input);
    tr.appendChild(period_td);

    container.appendChild(tr);
}

window.onload = addEvent();
