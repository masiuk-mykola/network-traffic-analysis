import type { ZodType } from 'zod'

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
  zListColumnsResponse,
  zListFieldsResponse,
  zListSensorsResponse,
} from './generated/zod.gen'

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
  [/^\/v1\/meta\/columns$/, zListColumnsResponse],
  [/^\/v1\/meta\/enums\/[^/]+$/, zGetEnumResponse],
  [/^\/v1\/meta\/schema\/[^/]+$/, zGetProtocolSchemaResponse],
  [/^\/v1\/estimate$/, zGetEstimateResponse],
  [/^\/v1\/searches\/[^/]+\/results$/, zGetSearchResultsResponse],
  [/^\/v1\/searches\/[^/]+$/, zGetSearchResponse],
  [/^\/v1\/sessions\/[^/]+\/flow$/, zGetSessionFlowResponse],
  [/^\/v1\/sessions\/[^/]+$/, zGetSessionResponse],
]

export function schemaForPath(path: string): ZodType | undefined {
  return ROUTES.find(([pattern]) => pattern.test(path))?.[1]
}
