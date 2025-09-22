private struct EarthscopeCard: View {
    let title: String?
    let caption: String?
    let images: EarthscopeImages?
    let bodyMarkdown: String?
    @State private var showDetail: Bool = false

    var body: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                if let t = title, !t.isEmpty {
                    Text(t).font(.headline)
                }
                if let c = caption, !c.isEmpty {
                    Text(c).font(.subheadline).foregroundColor(.secondary)
                }
                if let md = bodyMarkdown, !md.isEmpty {
                    Button {
                        showDetail = true
                    } label: {
                        Text("Read more")
                            .font(.footnote)
                            .underline()
                    }
                }
                if let imgs = images {
                    HStack(spacing: 8) {
                        if let url = URL(string: imgs.caption ?? "") {
                            Link(destination: url) {
                                AsyncImage(url: url) { img in img.resizable().scaledToFill() } placeholder: { ProgressView() }
                                    .frame(width: 64, height: 64)
                                    .clipped()
                                    .cornerRadius(8)
                            }
                        }
                        if let url = URL(string: imgs.stats ?? "") {
                            Link(destination: url) {
                                AsyncImage(url: url) { img in img.resizable().scaledToFill() } placeholder: { ProgressView() }
                                    .frame(width: 64, height: 64)
                                    .clipped()
                                    .cornerRadius(8)
                            }
                        }
                        if let url = URL(string: imgs.affects ?? "") {
                            Link(destination: url) {
                                AsyncImage(url: url) { img in img.resizable().scaledToFill() } placeholder: { ProgressView() }
                                    .frame(width: 64, height: 64)
                                    .clipped()
                                    .cornerRadius(8)
                            }
                        }
                        if let url = URL(string: imgs.playbook ?? "") {
                            Link(destination: url) {
                                AsyncImage(url: url) { img in img.resizable().scaledToFill() } placeholder: { ProgressView() }
                                    .frame(width: 64, height: 64)
                                    .clipped()
                                    .cornerRadius(8)
                            }
                        }
                    }
                }
            }
        }
        .sheet(isPresented: $showDetail) {
            EarthscopeDetailView(title: title, bodyMarkdown: bodyMarkdown)
        }
    }
}

private struct EarthscopeDetailView: View {
    let title: String?
    let bodyMarkdown: String?

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let t = title, !t.isEmpty {
                        Text(t).font(.title3).bold()
                    }
                    if let md = bodyMarkdown, !md.isEmpty {
                        // SwiftUI Text supports basic Markdown formatting
                        Text(md)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        Text("No content available.")
                            .foregroundColor(.secondary)
                    }
                }
                .padding()
            }
            .navigationTitle("Earthscope")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

EarthscopeCard(
    title: f.post_title,
    caption: f.post_caption,
    images: f.earthscope_images,
    bodyMarkdown: f.post_body
)