import {createContext} from 'react';
import type {LocationDescriptor} from 'history';

type ChildTransaction = {
  eventSlug: string;
  id: string;
  'project.name': string;
  transaction: string;
};

export type SpanEntryContextChildrenProps = {
  getViewChildTransactionTarget: (
    props: ChildTransaction
  ) => LocationDescriptor | undefined;
};

export const SpanEntryContext = createContext<SpanEntryContextChildrenProps>({
  getViewChildTransactionTarget: () => undefined,
});
