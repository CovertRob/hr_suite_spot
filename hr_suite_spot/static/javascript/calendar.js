document.addEventListener("DOMContentLoaded", function() {
    document.querySelectorAll("input[type='checkbox']").forEach(checkbox => {
        checkbox.addEventListener("click", function() {
            this.previousElementSibling.remove();
        });
    });
});
