document.addEventListener('DOMContentLoaded', function() {
  // Get user's timezone or default to browser's timezone
  let userTimezone = moment.tz.guess();
  
  // Get the appointments data from the data attribute
  const appointmentPickerElement = document.getElementById('appointment-picker');
  const availableTimesUTC = JSON.parse(appointmentPickerElement.dataset.appointments);
  
  // Initialize timezone selector if present
  const timezoneSelector = document.getElementById('timezone-selector');
  if (timezoneSelector) {
      // Populate with common timezones or use a pre-populated select
      userTimezone = timezoneSelector.value || userTimezone;
      
      timezoneSelector.addEventListener('change', function() {
          displayTimezoneInfo(this.value);
          userTimezone = this.value;
          updateAvailableTimes(availableTimesUTC, userTimezone);
      });
  }
  
  // Store the user's timezone in a hidden field for server submission
  const timezoneInput = document.createElement('input');
  timezoneInput.type = 'hidden';
  timezoneInput.id = 'user-timezone';
  timezoneInput.name = 'user_timezone';
  timezoneInput.value = userTimezone;
  document.getElementById('appointment-form').appendChild(timezoneInput);
  
  // Initial update of available times based on user's timezone
  updateAvailableTimes(availableTimesUTC, userTimezone);
  
  // Function to update available times based on timezone
  function updateAvailableTimes(utcTimes, timezone) {
      // Convert UTC times to the user's timezone
      const localTimes = utcTimes.map(timeStr => {
          return moment.utc(timeStr).tz(timezone).format('YYYY-MM-DD HH:mm');
      });
      
      // Create a mapping of dates to available times
      const availableTimeMap = {};
      localTimes.forEach(timeStr => {
          // Split the date and time parts
          const [datePart, timePart] = timeStr.split(' ');
          if (!availableTimeMap[datePart]) {
              availableTimeMap[datePart] = [];
          }
          availableTimeMap[datePart].push(timePart);
      });
      
      // Get unique dates
      const availableDates = Object.keys(availableTimeMap);
      
      // Clear the time select dropdown
      const timeSelect = document.getElementById('time-select');
      if (!timeSelect) {
          // Create a dropdown for time selection if it doesn't exist
          const newTimeSelect = document.createElement('select');
          newTimeSelect.id = 'time-select';
          newTimeSelect.style.display = 'none';
          newTimeSelect.addEventListener('change', function() {
              const selectedDate = document.getElementById('appointment-picker').value;
              const selectedTime = this.value;
              if (selectedDate && selectedTime) {
                  document.getElementById('selected-datetime').value = `${selectedDate} ${selectedTime}`;
              }
          });
          appointmentPickerElement.after(newTimeSelect);
      }
      
      // Reinitialize or update flatpickr
      if (window.appointmentPicker) {
          window.appointmentPicker.destroy();
      }
      
      window.appointmentPicker = flatpickr("#appointment-picker", {
          enableTime: false,
          dateFormat: "Y-m-d",
          minDate: "today",
          enable: availableDates,
          onChange: function(selectedDates, dateStr) {
              const timeSelect = document.getElementById('time-select');
              timeSelect.innerHTML = '';
              
              if (selectedDates.length > 0) {
                  // Get available times for selected date
                  const times = availableTimeMap[dateStr] || [];
                  
                  // Add a default option
                  const defaultOption = document.createElement('option');
                  defaultOption.value = '';
                  defaultOption.textContent = 'Select time';
                  timeSelect.appendChild(defaultOption);
                  
                  // Add time options
                  times.forEach(time => {
                      const option = document.createElement('option');
                      option.value = time;
                      option.textContent = time;
                      timeSelect.appendChild(option);
                  });
                  
                  // Show the time dropdown
                  timeSelect.style.display = 'block';
                  timeSelect.style.position = 'relative';
                  timeSelect.style.left = '45%';
              } else {
                  // Hide the time dropdown if no date is selected
                  timeSelect.style.display = 'none';
                  document.getElementById('selected-datetime').value = '';
              }
          }
      });
      
      // Display current timezone info
      const timezoneInfo = document.getElementById('timezone-info');
      if (timezoneInfo) {
          timezoneInfo.textContent = `Times shown in ${timezone} (${moment().tz(timezone).format('z')})`;
      }
  }
  
  // Add form submission validation
  document.getElementById("appointment-form").addEventListener("submit", function(event) {
      const selectedDateTime = document.getElementById("selected-datetime").value;
      const convertedToUTC = moment.tz(selectedDateTime, userTimezone).utc().format('YYYY-MM-DD HH:mm');
      
      if (!availableTimesUTC.includes(convertedToUTC)) {
          event.preventDefault();
          document.getElementById("validation-message").style.display = "block";
          return false;
      }
      
      // Store the selected time in UTC for submission
      const utcDateTimeInput = document.createElement('input');
      utcDateTimeInput.type = 'hidden';
      utcDateTimeInput.name = 'selected_datetime_utc';
      utcDateTimeInput.value = convertedToUTC;
      this.appendChild(utcDateTimeInput);
  });
  function displayTimezoneInfo(timezone) {
    const timezoneInfo = document.getElementById('timezone-info');
    if (timezoneInfo) {
        // Get current time in the timezone for display
        const currentTime = moment().tz(timezone);
        
        // Format with timezone abbreviation (EST, PST, etc.)
        const tzAbbr = currentTime.format('z');
        
        // Display timezone info
        timezoneInfo.textContent = `Appointment times are shown in ${timezone} (${tzAbbr})`;
    }
}

});