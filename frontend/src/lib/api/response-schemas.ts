import { z, type ZodType } from 'zod'

import {
  zGetEnumResponse,
  zGetEstimateResponse,
  zGetHealthResponse,
  zGetMeResponse,
  zGetProtocolSchemaResponse,
  zGetSearchResponse,
  zGetSearchResultsResponse,
  zGetSessionFlowResponse,
  zGetSessionResponse,
  zListRelatedSessionsResponse,
  zListFieldsResponse,
  zListSensorsResponse,
} from './generated/zod.gen'

/**
 * The server publishes a column type the contract does not list (`geo_hint`), so the generated
 * enum would reject a perfectly good body. The column type is only ever read as a string, so this
 * checks the shape and leaves the vocabulary open.
 */
const zColumnList = z.object({
  items: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      type: z.string(),
      default_visible: z.boolean(),
      sortable: z.boolean(),
      width_hint: z.int(),
    }),
  ),
})

/**
 * The reads the proxy knows how to check. An unmapped path is passed through unvalidated on
 * purpose — better an unchecked body than a guessed schema. Add a row when a screen starts
 * depending on a new read.
 */
const ROUTES: ReadonlyArray<readonly [RegExp, ZodType]> = [
  [/^\/v1\/health$/, zGetHealthResponse],
  [/^\/v1\/me$/, zGetMeResponse],
  [/^\/v1\/sensors$/, zListSensorsResponse],
  [/^\/v1\/meta\/fields$/, zListFieldsResponse],
  [/^\/v1\/meta\/columns$/, zColumnList],
  [/^\/v1\/meta\/enums\/[^/]+$/, zGetEnumResponse],
  [/^\/v1\/meta\/schema\/[^/]+$/, zGetProtocolSchemaResponse],
  [/^\/v1\/estimate$/, zGetEstimateResponse],
  [/^\/v1\/searches\/[^/]+\/results$/, zGetSearchResultsResponse],
  [/^\/v1\/searches\/[^/]+$/, zGetSearchResponse],
  [/^\/v1\/sessions\/[^/]+\/flow$/, zGetSessionFlowResponse],
  [/^\/v1\/sessions\/[^/]+\/related$/, zListRelatedSessionsResponse],
  [/^\/v1\/sessions\/[^/]+$/, zGetSessionResponse],
]

export function schemaForPath(path: string): ZodType | undefined {
  return ROUTES.find(([pattern]) => pattern.test(path))?.[1]
}
