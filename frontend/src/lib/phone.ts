/**
 * Shared phone-number helpers so every place that collects a phone number
 * captures an explicit country code (never free-text-only). The UI pairs a
 * dial-code <select> with a national-number input, then composes a full
 * E.164 string on submit.
 */

export interface DialCode {
  code: string;
  label: string;
}

// Common country dial codes. India (+91) first since this deployment serves
// Indian clinics; extend as needed.
export const DIAL_CODES: DialCode[] = [
  { code: "+91", label: "India +91" },
  { code: "+1", label: "US/Canada +1" },
  { code: "+44", label: "UK +44" },
  { code: "+971", label: "UAE +971" },
  { code: "+65", label: "Singapore +65" },
  { code: "+61", label: "Australia +61" },
  { code: "+49", label: "Germany +49" },
  { code: "+33", label: "France +33" },
  { code: "+880", label: "Bangladesh +880" },
  { code: "+94", label: "Sri Lanka +94" },
  { code: "+977", label: "Nepal +977" },
];

export const DEFAULT_DIAL_CODE = "+91";

/** Strip everything but digits, and drop any leading zeros (national trunk prefix). */
export function nationalDigits(input: string): string {
  return input.replace(/[^0-9]/g, "").replace(/^0+/, "");
}

/** Compose a full E.164 number from a dial code + a national-number input. */
export function toE164(dialCode: string, input: string): string {
  return `${dialCode}${nationalDigits(input)}`;
}
