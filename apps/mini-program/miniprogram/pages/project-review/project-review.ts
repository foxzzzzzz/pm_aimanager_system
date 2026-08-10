import { api } from "../../services/api";
import type { ProductSpec, ProjectMember, ProjectReview } from "../../types";

type ReviewTab = "specs" | "members" | "raci";

interface TabTapEvent {
  currentTarget: { dataset: { tab: ReviewTab } };
}

interface SpecView extends ProductSpec {
  detail: string;
}

interface RaciView {
  code: string;
  name: string;
  output: string;
  roles: Array<{ key: "R" | "A" | "C" | "I"; names: string }>;
}

const valueOrEmpty = (value: string | null) => value?.trim() || "";

Page({
  data: {
    projectId: "",
    review: null as ProjectReview | null,
    specs: [] as SpecView[],
    members: [] as ProjectMember[],
    raciRows: [] as RaciView[],
    activeTab: "specs" as ReviewTab,
    loading: true,
  },
  async onLoad(options: Record<string, string | undefined>) {
    const projectId = options.projectId || wx.getStorageSync<string>("current_project_id");
    this.setData({ projectId });
    try {
      const review = await api.projectReview(projectId);
      const specs = review.product_specs.map((spec) => ({
        ...spec,
        detail: [spec.configuration, spec.core_information, spec.selected_model]
          .map(valueOrEmpty)
          .filter(Boolean)
          .join(" · ") || "—",
      }));
      const raciRows = review.milestones.map((milestone) => ({
        code: milestone.code,
        name: milestone.name,
        output: milestone.output || "—",
        roles: (["R", "A", "C", "I"] as const).map((key) => ({
          key,
          names: milestone.assignments[key]?.join("、") || "—",
        })),
      }));
      this.setData({ review, specs, members: review.members, raciRows });
    } catch (error) {
      wx.showToast({ title: (error as Error).message || "项目资料加载失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  selectTab(event: TabTapEvent) {
    this.setData({ activeTab: event.currentTarget.dataset.tab });
  },
});
