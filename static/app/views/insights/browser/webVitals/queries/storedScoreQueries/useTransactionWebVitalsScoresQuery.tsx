import type {Sort} from 'sentry/utils/discover/fields';
import {MutableSearch} from 'sentry/utils/tokenizeSearch';
import {getWebVitalScoresFromTableDataRow} from 'sentry/views/insights/browser/webVitals/queries/storedScoreQueries/getWebVitalScoresFromTableDataRow';
import type {
  Opportunity,
  Score,
  WebVitals,
} from 'sentry/views/insights/browser/webVitals/types';
import type {BrowserType} from 'sentry/views/insights/browser/webVitals/utils/queryParameterDecoders/browserType';
import {useDefaultWebVitalsQuery} from 'sentry/views/insights/browser/webVitals/utils/useDefaultQuery';
import {useWebVitalsSort} from 'sentry/views/insights/browser/webVitals/utils/useWebVitalsSort';
import {useMetrics} from 'sentry/views/insights/common/queries/useDiscover';
import {useInsightsEap} from 'sentry/views/insights/common/utils/useEap';
import {
  type MetricsProperty,
  SpanIndexedField,
  type SubregionCode,
} from 'sentry/views/insights/types';

type Props = {
  browserTypes?: BrowserType[];
  defaultSort?: Sort;
  enabled?: boolean;
  limit?: number;
  query?: string;
  shouldEscapeFilters?: boolean;
  sortName?: string;
  subregions?: SubregionCode[];
  transaction?: string | null;
  webVital?: WebVitals | 'total';
};

export const useTransactionWebVitalsScoresQuery = ({
  limit,
  transaction,
  defaultSort,
  sortName = 'sort',
  webVital = 'total',
  enabled,
  query,
  shouldEscapeFilters = true,
  browserTypes,
  subregions,
}: Props) => {
  const sort = useWebVitalsSort({sortName, defaultSort});
  const defaultQuery = useDefaultWebVitalsQuery();

  const useEap = useInsightsEap();

  const totalOpportunityScoreField = (
    useEap ? 'opportunity_score(measurements.score.total)' : 'total_opportunity_score()'
  ) satisfies MetricsProperty;

  if (sort !== undefined) {
    if (sort.field === 'avg(measurements.score.total)') {
      sort.field = 'performance_score(measurements.score.total)';
    }
    if (
      [
        'opportunity_score(measurements.score.total)',
        'total_opportunity_score()',
      ].includes(sort.field)
    ) {
      sort.field = totalOpportunityScoreField;
    }
  }

  const search = new MutableSearch([
    'avg(measurements.score.total):>=0',
    ...(query ? [query] : []),
  ]);
  if (transaction) {
    search.addFilterValue('transaction', transaction, shouldEscapeFilters);
  }
  if (browserTypes) {
    search.addDisjunctionFilterValues(SpanIndexedField.BROWSER_NAME, browserTypes);
  }
  if (subregions) {
    search.addDisjunctionFilterValues(SpanIndexedField.USER_GEO_SUBREGION, subregions);
  }

  const {data, isPending, ...rest} = useMetrics(
    {
      limit: limit ?? 50,
      search: [defaultQuery, search.formatString()].join(' ').trim(),
      sorts: [sort],
      enabled,
      fields: [
        'project.id',
        'project',
        'transaction',
        'p75(measurements.lcp)',
        'p75(measurements.fcp)',
        'p75(measurements.cls)',
        'p75(measurements.ttfb)',
        'p75(measurements.inp)',
        ...(webVital === 'total'
          ? []
          : [`performance_score(measurements.score.${webVital})` as const]),
        `opportunity_score(measurements.score.${webVital})`,
        'performance_score(measurements.score.total)',
        'count()',
        `count_scores(measurements.score.lcp)`,
        `count_scores(measurements.score.fcp)`,
        `count_scores(measurements.score.cls)`,
        `count_scores(measurements.score.inp)`,
        `count_scores(measurements.score.ttfb)`,
        `count_scores(measurements.score.total)`,
        totalOpportunityScoreField,
      ],
    },
    'api.performance.browser.web-vitals.transactions-scores'
  );

  const tableData: Array<
    (typeof data)[0] & {
      'avg(measurements.score.total)': number;
    } & Opportunity &
      Score
  > = data.map(row => {
    // Map back performance score key so we don't have to handle both keys in the UI
    const finalRow = {
      ...row,
      'avg(measurements.score.total)': row['performance_score(measurements.score.total)'],
    };
    const {totalScore, clsScore, fcpScore, lcpScore, ttfbScore, inpScore} =
      getWebVitalScoresFromTableDataRow(finalRow);
    return {
      ...finalRow,
      totalScore: totalScore ?? 0,
      clsScore: clsScore ?? 0,
      fcpScore: fcpScore ?? 0,
      lcpScore: lcpScore ?? 0,
      ttfbScore: ttfbScore ?? 0,
      inpScore: inpScore ?? 0,
      'avg(measurements.score.total)': row['performance_score(measurements.score.total)'],
      // Map back opportunity score key so we don't have to handle both keys in the UI
      opportunity:
        row[
          webVital === 'total'
            ? totalOpportunityScoreField
            : (`opportunity_score(measurements.score.${webVital})` as const)
        ],
    };
  });

  return {
    data: tableData,
    isPending,
    ...rest,
  };
};
