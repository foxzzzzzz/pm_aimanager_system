const isCompleted = (milestone) => Boolean(milestone.actual_completion?.end_date);

const isApplicable = (milestone) =>
  Boolean(milestone.plan) && milestone.plan.state !== "not_applicable";

const addDays = (dateText, days) => {
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};

const predicates = {
  all: () => true,
  completed: (milestone) => isCompleted(milestone),
  todo: (milestone) => !isCompleted(milestone) && isApplicable(milestone),
  upcoming: (milestone, today, upcomingDays) => {
    const endDate = milestone.plan?.end_date;
    return Boolean(
      !isCompleted(milestone)
      && isApplicable(milestone)
      && endDate
      && endDate >= today
      && endDate <= addDays(today, upcomingDays),
    );
  },
  overdue: (milestone, today) => {
    const endDate = milestone.plan?.end_date;
    return Boolean(
      !isCompleted(milestone)
      && isApplicable(milestone)
      && endDate
      && endDate < today,
    );
  },
};

const filterDefinitions = [
  { key: "todo", label: "待办" },
  { key: "upcoming", label: "近期" },
  { key: "overdue", label: "逾期" },
  { key: "completed", label: "已完成" },
  { key: "all", label: "全部" },
];

export const filterMilestones = (milestones, key, today, upcomingDays = 3) => {
  const predicate = predicates[key] || predicates.all;
  return milestones.filter((milestone) => predicate(milestone, today, upcomingDays));
};

export const buildMilestoneFilters = (milestones, today, upcomingDays = 3) =>
  filterDefinitions.map((filter) => ({
    ...filter,
    count: filterMilestones(milestones, filter.key, today, upcomingDays).length,
  }));
