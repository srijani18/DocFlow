/* Generated from schemas/ by make gen-schemas. Do not edit. */

/**
 * An amount as printed, with its currency.
 */
export interface Money {
  /**
   * The amount as a number, without currency symbols or thousands separators.
   */
  amount: number | null;
  /**
   * ISO 4217 code, e.g. INR.
   */
  currency: string | null;
}
