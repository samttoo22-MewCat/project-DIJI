const AGE_COOKIE_NAME = "diji_age_confirmed";
const AGE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

function hasAgeConfirmationCookie() {
  return document.cookie.split(";").some((part) => part.trim() === `${AGE_COOKIE_NAME}=1`);
}

function rememberAgeConfirmation() {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${AGE_COOKIE_NAME}=1; Max-Age=${AGE_COOKIE_MAX_AGE}; Path=/; SameSite=Lax${secure}`;
}

const ageDialog = document.querySelector("#age-confirmation");
const ageAccepted = document.querySelector("#age-confirmation-accepted");
const ageRemember = document.querySelector("#age-confirmation-remember");
const ageSubmit = document.querySelector("#age-confirmation-submit");

if (ageDialog && ageAccepted && ageRemember && ageSubmit && !hasAgeConfirmationCookie()) {
  ageDialog.showModal();
  ageDialog.addEventListener("cancel", (event) => event.preventDefault());
  ageAccepted.addEventListener("change", () => { ageSubmit.disabled = !ageAccepted.checked; });
  ageSubmit.addEventListener("click", () => {
    if (!ageAccepted.checked) return;
    if (ageRemember.checked) rememberAgeConfirmation();
    ageDialog.close();
  });
}
