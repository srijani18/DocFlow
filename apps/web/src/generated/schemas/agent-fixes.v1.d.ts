/* Generated from schemas/ by make gen-schemas. Do not edit. */

/**
 * Corrected values the validation agent's model proposes after rereading the document (F6).
 */
export interface AgentFixes {
  /**
   * One entry per field whose printed value differs from the current value. Empty if nothing was misread.
   */
  fixes: {
    /**
     * Dotted field path, as given in the request.
     */
    path: string;
    /**
     * The value exactly as printed (numbers without separators).
     */
    value: string | number | null;
    confidence: number;
    /**
     * What was misread, briefly.
     */
    reason: string;
  }[];
}
