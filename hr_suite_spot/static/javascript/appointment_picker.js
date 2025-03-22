document.addEventListener('DOMContentLoaded', function() {
    // Get the appointments data from the data attribute
    const appointmentPickerElement = document.getElementById('appointment-picker');
    const availableTimes = JSON.parse(appointmentPickerElement.dataset.appointments);
    
    // Create a mapping of dates to available times
    const availableTimeMap = {};
    availableTimes.forEach(timeStr => {
      // Split the date and time parts
      const [datePart, timePart] = timeStr.split(' ');
      if (!availableTimeMap[datePart]) {
        availableTimeMap[datePart] = [];
      }
      availableTimeMap[datePart].push(timePart);
    });
    
    // Get unique dates
    const availableDates = Object.keys(availableTimeMap);
    
    // Create a dropdown for time selection
    const timeSelect = document.createElement('select');
    timeSelect.id = 'time-select';
    timeSelect.style.display = 'none';
    timeSelect.addEventListener('change', function() {
      const selectedDate = document.getElementById('appointment-picker').value;
      const selectedTime = this.value;
      if (selectedDate && selectedTime) {
        document.getElementById('selected-datetime').value = `${selectedDate} ${selectedTime}`;
      }
    });
    appointmentPickerElement.after(timeSelect);
    
    // Initialize flatpickr for date selection only
    const picker = flatpickr("#appointment-picker", {
      enableTime: false, // Disable built-in time picker
      dateFormat: "Y-m-d",
      minDate: "today",
      
      // Only enable dates with available slots
      enable: availableDates,
      
      // When a date is selected, populate the time dropdown
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
    
    // Add form submission validation
    document.getElementById("appointment-form").addEventListener("submit", function(event) {
      const selectedDateTime = document.getElementById("selected-datetime").value;
      
      if (!availableTimes.includes(selectedDateTime)) {
        event.preventDefault();
        document.getElementById("validation-message").style.display = "block";
        return false;
      }
    });
  });