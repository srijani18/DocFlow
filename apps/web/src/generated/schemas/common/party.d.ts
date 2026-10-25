/* Generated from schemas/ by make gen-schemas. Do not edit. */

/**
 * A seller, buyer or merchant.
 */
export interface Party {
  /**
   * Legal or trading name.
   */
  name: string | null;
  /**
   * 15-character Indian GSTIN, or null if absent.
   */
  gstin: string | null;
  /**
   * Postal address, or null if absent.
   */
  address: Address | null;
}
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
