/* Generated from schemas/ by make gen-schemas. Do not edit. */

export interface Address {
  /**
   * First address line.
   */
  line1: string | null;
  /**
   * Second address line.
   */
  line2: string | null;
  /**
   * City.
   */
  city: string | null;
  /**
   * State or province.
   */
  state: string | null;
  /**
   * PIN or postal code.
   */
  postal_code: string | null;
  /**
   * Country.
   */
  country: string | null;
}
