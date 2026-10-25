/* Generated from schemas/ by make gen-schemas. Do not edit. */

/**
 * What the model returns: the document data plus a confidence per field. `data` is checked against the document type's own schema.
 */
export interface ExtractionEnvelope {
  /**
   * An instance of the document type's schema.
   */
  data: {
    [k: string]: unknown;
  };
  /**
   * How sure the model is about each extracted field.
   */
  confidence: {
    /**
     * Dotted path with zero-based indices, e.g. vendor.gstin or line_items.0.amount.amount.
     */
    field: string;
    /**
     * Probability from 0 to 1 that the value is correct.
     */
    score: number;
  }[];
}
