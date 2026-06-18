document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-confirm]").forEach((element) => {
        element.addEventListener("click", (event) => {
            if (!window.confirm(element.getAttribute("data-confirm"))) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll("select[data-searchable='true']").forEach((select) => {
        const search = document.createElement("input");
        search.type = "search";
        search.className = "form-control search-box";
        search.placeholder = "Rechercher...";
        select.parentNode.insertBefore(search, select);

        const options = Array.from(select.options).map((option) => ({
            option,
            text: option.text.toLowerCase(),
        }));

        search.addEventListener("input", () => {
            const query = search.value.trim().toLowerCase();
            options.forEach(({ option, text }) => {
                option.hidden = query && !text.includes(query);
            });
        });
    });
});
